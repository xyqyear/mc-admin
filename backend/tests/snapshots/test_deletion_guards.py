import asyncio
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.background_tasks import TaskProgress, TaskType
from app.background_tasks.types import TaskStatus
from app.operation_admission import get_server_write_admission
from app.runtime_resources import current_runtime
from app.servers.crud import get_active_server_by_id
from app.servers.lifecycle.orchestrators import remove_server_full
from app.servers.models import ServerStatus
from app.servers.tasks import submit_lifecycle
from app.snapshots.scopes import GlobalScope, PathsScope

pytestmark = pytest.mark.binary("restic")


@pytest.mark.parametrize("action", ["create", "preview"])
@pytest.mark.parametrize("global_scope", [False, True])
@pytest.mark.parametrize("entry", ["admission", "execution"])
async def test_delete_refuses_accepted_snapshots_without_cancelling_other_work(
    case, monkeypatch, global_scope, entry, action
):
    target = case.data / "keep.txt"
    target.write_text("must survive")
    source = await case.snapshots.create_snapshot([case.data.parent.parent]) if action == "preview" else None
    started, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def unrelated():
        started.set()
        try:
            await release.wait()
            yield TaskProgress(progress=100, message="完成")
        except asyncio.CancelledError:
            cancelled.set()
            raise

    other = case.tasks.submit(TaskType.CHUNK_PRUNE_PREVIEW, "unrelated", unrelated(), server_id="survival")
    await asyncio.wait_for(started.wait(), 5)

    start = case.journal.start

    async def paused(operation_id):
        record = await case.journal.get(operation_id)
        if record.kind in {"snapshot_create", "snapshot_preview"}:
            await asyncio.Event().wait()
        else:
            await start(operation_id)

    monkeypatch.setattr(case.journal, "start", paused)
    scope = GlobalScope() if global_scope else PathsScope(server_id="survival", paths=("keep.txt",))
    if source is None:
        accepted = await case.commands.create(scope, 1)
    else:
        previews = current_runtime().snapshot_previews
        assert previews is not None
        accepted = await previews.submit(scope, source.id, 1)
    try:
        with pytest.raises(HTTPException) as rejected:
            if entry == "admission":
                await submit_lifecycle("survival", "remove", 1)
            else:
                async with current_runtime().database.session_factory() as session:
                    await remove_server_full(session, "survival", user_id=1)
        assert rejected.value.status_code == 423
        assert cast(dict, rejected.value.detail)["task_id"] == accepted["task_id"]
        assert not cancelled.is_set() and not other.awaitable.done()
        assert target.read_text() == "must survive"
        assert case.tasks.get_task(accepted["task_id"]).status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        assert not get_server_write_admission().is_frozen("survival")
    finally:
        release.set()
        await other.awaitable
        await case.tasks.cancel(accepted["task_id"])
        await case.tasks.get_future(accepted["task_id"])


async def test_snapshot_admission_during_delete_drain_is_rejected_before_acceptance(case, monkeypatch):
    target = case.data / "keep.txt"
    target.write_text("retained until deletion")
    entered, release = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(case.instance, "created", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(case.instance, "remove", AsyncMock(), raising=False)

    async def drain(_):
        entered.set()
        await release.wait()
        raise HTTPException(status_code=409, detail="controlled drain timeout")

    monkeypatch.setattr("app.servers.lifecycle.orchestrators.cancel_and_wait_for_tasks", drain)
    async with current_runtime().database.session_factory() as session:
        deletion = asyncio.create_task(remove_server_full(session, "survival", user_id=1))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            for scope in (GlobalScope(), PathsScope(server_id="survival", paths=("keep.txt",))):
                with pytest.raises(HTTPException) as rejected:
                    await case.commands.create(scope, 1)
                assert rejected.value.status_code == 423
            release.set()
            with pytest.raises(HTTPException) as stopped:
                await deletion
            assert stopped.value.status_code == 409
        finally:
            release.set()
            if not deletion.done():
                deletion.cancel()
                await asyncio.gather(deletion, return_exceptions=True)
    case.instance.remove.assert_not_awaited()
    assert target.read_text() == "retained until deletion"
    assert not get_server_write_admission().is_frozen("survival")
    async with current_runtime().database.session_factory() as session:
        row = await get_active_server_by_id(session, "survival")
        assert row is not None and row.status is ServerStatus.ACTIVE


async def test_delete_rechecks_snapshots_accepted_after_its_own_admission(case, monkeypatch):
    target = case.data / "keep.txt"
    target.write_text("protected by later accepted backup")
    monkeypatch.setattr(case.instance, "created", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(case.instance, "remove", AsyncMock(), raising=False)
    entered, release_delete = asyncio.Event(), asyncio.Event()
    start = case.journal.start

    async def delayed(operation_id):
        record = await case.journal.get(operation_id)
        if record.kind == "server_remove":
            entered.set()
            await release_delete.wait()
            await start(operation_id)
        else:
            await asyncio.Event().wait()

    monkeypatch.setattr(case.journal, "start", delayed)
    deletion = await submit_lifecycle("survival", "remove", 1)
    await asyncio.wait_for(entered.wait(), 5)
    backup = await case.commands.create(GlobalScope(), 1)
    try:
        release_delete.set()
        result = await asyncio.wait_for(case.tasks.get_future(deletion.task_id), 10)
        assert not result.success
        assert case.tasks.get_task(deletion.task_id).status is TaskStatus.FAILED
        assert case.tasks.get_task(backup["task_id"]).status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        assert not case.tasks.get_future(backup["task_id"]).done()
        case.instance.remove.assert_not_awaited()
        assert target.read_text() == "protected by later accepted backup"
        assert not get_server_write_admission().is_frozen("survival")
    finally:
        release_delete.set()
        await case.tasks.cancel(backup["task_id"])
        await case.tasks.get_future(backup["task_id"])
