import asyncio
import json
from contextlib import aclosing
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks import (
    BackgroundTaskManager,
    TaskProgress,
    TaskStatus,
    TaskType,
)
from app.background_tasks.models import BackgroundTask
from app.errors import INTERNAL_ERROR_MESSAGE, PublicOperationError
from app.operations.journal_types import JournalLimits, OperationSpec, ResourceReference


async def complete(value: int):
    yield TaskProgress(progress=100, result={"value": value})


async def test_settled_handles_release_and_recent_history_is_bounded(journal):
    manager = BackgroundTaskManager(journal)
    manager.RECENT_TASK_LIMIT = 2
    held = asyncio.Event()

    async def active():
        await held.wait()
        yield TaskProgress(result={"active": True})

    pending = await manager.submit_durable(TaskType.SELF_CHECK, "运行中的任务", active())
    accepted = []
    try:
        for value in range(5):
            task = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(value))
            assert (await task.awaitable).success
            accepted.append(task)
        await asyncio.gather(*(worker for identity, worker in manager._asyncio_tasks.items() if identity != pending.task_id))
        tasks = manager.get_all_tasks()
        assert {task.task_id for task in tasks} == {pending.task_id, accepted[-2].task_id, accepted[-1].task_id}
        assert set(manager._asyncio_tasks) == {pending.task_id}
        assert set(manager._futures) == {pending.task_id}
        assert manager.get_future(pending.task_id) is pending.awaitable
        completed = manager.get_future(accepted[-1].task_id)
        assert completed is not None and (await completed).data == {"value": 4}
        detail = await manager.get_task_detail(accepted[0].task_id)
        assert detail is not None and detail.result == {"value": 0}
        assert accepted[0].task_id not in {task.task_id for task in manager.get_all_tasks()}
    finally:
        held.set()
        await manager.shutdown()


async def test_journal_capacity_eviction_removes_live_projection_and_detail(journal):
    journal.limits = JournalLimits(max_records=2)
    manager = BackgroundTaskManager(journal)
    try:
        first = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(0))
        await first.awaitable
        async with aclosing(manager.events()) as stream:
            assert first.task_id in {task["task_id"] for task in json.loads((await anext(stream))[6:])["tasks"]}
            for value in range(1, 3):
                task = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(value))
                await task.awaitable
            assert manager.get_task(first.task_id) is None
            assert await manager.get_task_detail(first.task_id) is None
            assert {task.task_id for task in manager.get_all_tasks()} == {record.operation_id for record in await journal.list()}
        async with aclosing(manager.events()) as stream:
            assert first.task_id not in {task["task_id"] for task in json.loads((await anext(stream))[6:])["tasks"]}
    finally:
        await manager.shutdown()


async def test_recent_age_eviction_does_not_delete_durable_result_or_active_work(journal):
    manager = BackgroundTaskManager(journal)
    accepted = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(2))
    await accepted.awaitable
    accepted.task.ended_at = datetime.now(UTC) - timedelta(minutes=31)
    active = BackgroundTask(task_id="active", task_type=TaskType.SELF_CHECK, name="仍在执行", status=TaskStatus.RUNNING,
                            created_at=datetime.now(UTC) - timedelta(days=1))
    manager._tasks[active.task_id] = active
    assert manager.get_all_tasks() == [active]
    detail = await manager.get_task_detail(accepted.task_id)
    assert detail is not None and detail.result == {"value": 2}
    manager._tasks.pop(active.task_id)
    await manager.shutdown()


async def test_rolled_back_admission_keeps_task_projection_and_durable_result(journal):
    manager = BackgroundTaskManager(journal)
    try:
        accepted = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(3))
        await accepted.awaitable
        duplicate = OperationSpec("dns_update", (ResourceReference("global"),), operation_id="duplicate")
        await journal.accept(duplicate)
        journal.clock = lambda: datetime.now(UTC) + timedelta(days=31)
        with pytest.raises(IntegrityError):
            await journal.accept(duplicate)
        assert manager.get_task(accepted.task_id) is accepted.task
        detail = await manager.get_task_detail(accepted.task_id)
        assert detail is not None and detail.result == {"value": 3}
    finally:
        await manager.shutdown()


@pytest.mark.parametrize("read_first", [True, False])
async def test_concurrent_retention_returns_complete_detail_or_absence(journal, monkeypatch, read_first):
    journal.limits = JournalLimits(max_records=1)
    manager = BackgroundTaskManager(journal)
    selected, release = asyncio.Event(), asyncio.Event()
    reader = None
    try:
        accepted = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(7))
        await accepted.awaitable
        assert manager.remove_task(accepted.task_id)
        execute = AsyncSession.execute

        async def hold_selected_result(session, statement, *args, **kwargs):
            result = await execute(session, statement, *args, **kwargs)
            if (getattr(statement, "is_select", False) and "operation_journal.task_result_json" in str(statement)
                    and not selected.is_set()):
                selected.set()
                await release.wait()
            return result

        monkeypatch.setattr(AsyncSession, "execute", hold_selected_result)
        if read_first:
            reader = asyncio.create_task(manager.get_task_detail(accepted.task_id))
            await asyncio.wait_for(selected.wait(), 2)
        await journal.accept(OperationSpec("dns_update", (ResourceReference("global"),), operation_id="replacement"))
        assert await journal.get(accepted.task_id) is None
        release.set()
        detail = await reader if reader is not None else await manager.get_task_detail(accepted.task_id)
        if read_first:
            assert detail is not None and detail.status is TaskStatus.COMPLETED and detail.result == {"value": 7}
            assert detail.ended_at is not None and detail.ended_at.tzinfo is UTC
        else:
            assert detail is None
    finally:
        release.set()
        if reader is not None:
            await asyncio.gather(reader, return_exceptions=True)
        await manager.shutdown()


@pytest.mark.parametrize("authored", [True, False])
async def test_restart_retains_only_safe_authored_failure(journal, authored):
    manager = BackgroundTaskManager(journal)
    message = "目标文件正在使用，请稍后重试" if authored else "raw-secret-provider-token"

    async def fail():
        raise PublicOperationError(message) if authored else RuntimeError(message)
        yield TaskProgress()

    try:
        accepted = await manager.submit_durable(TaskType.SELF_CHECK, "自检", fail())
        assert not (await accepted.awaitable).success
        record = await journal.get(accepted.task_id)
        assert record is not None
        assert record.failure_message == (message if authored else None)
        restored = BackgroundTaskManager(journal)
        try:
            restored.restore_history([record])
            detail = await restored.get_task_detail(accepted.task_id)
            assert detail is not None
            assert detail.error == (message if authored else "操作记录已恢复")
            assert accepted.task.error == (message if authored else INTERNAL_ERROR_MESSAGE)
        finally:
            await restored.shutdown()
    finally:
        await manager.shutdown()


@pytest.mark.parametrize("intermediate", [None, {"partial": True}])
async def test_detail_read_does_not_mix_later_settlement_with_earlier_result(journal, monkeypatch, intermediate):
    manager = BackgroundTaskManager(journal)
    ready, finish = asyncio.Event(), asyncio.Event()
    selected, release = asyncio.Event(), asyncio.Event()
    reader = None

    async def work():
        yield TaskProgress(progress=50, result=intermediate)
        ready.set()
        await finish.wait()
        yield TaskProgress(progress=100, result={"complete": True})

    try:
        accepted = await manager.submit_durable(TaskType.SELF_CHECK, "自检", work())
        await asyncio.wait_for(ready.wait(), 2)
        execute = AsyncSession.execute

        async def hold_selected_result(session, statement, *args, **kwargs):
            result = await execute(session, statement, *args, **kwargs)
            if (getattr(statement, "is_select", False) and "operation_journal.task_result_json" in str(statement)
                    and not selected.is_set()):
                selected.set()
                await release.wait()
            return result

        monkeypatch.setattr(AsyncSession, "execute", hold_selected_result)
        reader = asyncio.create_task(manager.get_task_detail(accepted.task_id))
        await asyncio.wait_for(selected.wait(), 2)
        finish.set()
        assert (await asyncio.wait_for(accepted.awaitable, 2)).success
        assert accepted.task.status is TaskStatus.COMPLETED
        release.set()
        earlier = await reader
        assert earlier is not None and earlier.status is TaskStatus.RUNNING
        assert earlier.result == intermediate and earlier.ended_at is None
        latest = await manager.get_task_detail(accepted.task_id)
        assert latest is not None and latest.status is TaskStatus.COMPLETED and latest.result == {"complete": True}
    finally:
        finish.set()
        release.set()
        if reader is not None:
            await asyncio.gather(reader, return_exceptions=True)
        await manager.shutdown()


async def test_restored_projection_keeps_only_recent_history_without_loading_results(journal):
    manager = BackgroundTaskManager(journal)
    manager.RECENT_TASK_LIMIT = 2
    try:
        for value in range(4):
            accepted = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(value))
            await accepted.awaitable
        restored = BackgroundTaskManager(journal)
        restored.RECENT_TASK_LIMIT = 2
        try:
            restored.restore_history(await journal.list(origin="task"))
            tasks = restored.get_all_tasks()
            assert len(tasks) == 2
            assert all(not task.result_known and task.result is None for task in tasks)
            old = replace((await journal.list())[0], legacy_id="old", ended_at=datetime.now(UTC) - timedelta(minutes=31))
            restored.restore_history([old])
            assert restored.get_task("old") is None
        finally:
            await restored.shutdown()
    finally:
        await manager.shutdown()


async def test_authored_history_finalization_failure_survives_restart_and_is_bounded(journal):
    manager = BackgroundTaskManager(journal)
    message = "无法保存恢复历史\n" + "重试" * 2000

    async def history_failed(_state):
        raise PublicOperationError(message)

    try:
        accepted = await manager.submit_durable(TaskType.SELF_CHECK, "自检", complete(1), on_finished=history_failed)
        assert not (await accepted.awaitable).success
        record = await journal.get(accepted.task_id)
        assert record is not None and record.failure_message is not None
        assert "\n" not in record.failure_message and len(record.failure_message.encode()) <= 4096
        restored = BackgroundTaskManager(journal)
        try:
            detail = await restored.get_task_detail(accepted.task_id)
            assert detail is not None and detail.error == record.failure_message
        finally:
            await restored.shutdown()
    finally:
        await manager.shutdown()
