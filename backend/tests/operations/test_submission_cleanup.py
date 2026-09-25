import asyncio

import pytest

from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskProgress, TaskType
from app.operations.journal_types import OperationState


async def test_rejected_submission_preserves_original_error_and_settles_after_close_failure(journal):
    manager = BackgroundTaskManager(journal)
    await manager.shutdown()
    cleanup_failure = OSError("synthetic unsubmitted generator cleanup failure")
    reached_external_work = False

    async def operation():
        nonlocal reached_external_work
        try:
            yield TaskProgress(message="prepared cleanup")
            reached_external_work = True
            yield TaskProgress(progress=100)
        finally:
            raise cleanup_failure

    generator = operation()
    await anext(generator)
    failure: BaseException | None = None
    try:
        try:
            await manager.submit_durable(
                TaskType.ARCHIVE_CREATE, "rejected submission", generator, task_id="rejected-close-failure",
            )
        except (RuntimeError, OSError, asyncio.CancelledError) as error:
            failure = error

        record = await journal.get("rejected-close-failure")
        assert record is not None
        assert record.state is OperationState.FAILED, f"Queued record survived cleanup error: {type(failure).__name__}"
        assert record.writers_stopped and record.ended_at is not None
        assert not record.processes and not reached_external_work
        assert await journal.unsettled() == []
        assert manager.get_task(record.operation_id) is None
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
        assert isinstance(failure, RuntimeError)
        assert str(failure) == "后台任务管理器正在关闭"
        assert failure.__cause__ is cleanup_failure
    finally:
        await generator.aclose()


async def test_rejected_submission_waits_for_cancelled_cleanup_and_settles(journal):
    manager = BackgroundTaskManager(journal)
    await manager.shutdown()
    cleaning, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    reached_external_work = False

    async def operation():
        nonlocal reached_external_work
        try:
            yield TaskProgress(message="prepared cleanup")
            reached_external_work = True
            yield TaskProgress(progress=100)
        finally:
            cleaning.set()
            await release.wait()
            closed.set()

    generator = operation()
    await anext(generator)

    async def submit() -> BaseException:
        try:
            await manager.submit_durable(
                TaskType.ARCHIVE_CREATE, "rejected submission", generator, task_id="rejected-cancelled-cleanup",
            )
        except (RuntimeError, OSError, asyncio.CancelledError) as error:
            return error
        pytest.fail("The stopped task manager accepted a new task")

    owner = asyncio.create_task(submit())
    try:
        await asyncio.wait_for(cleaning.wait(), 3)
        owner.cancel("cancel during rejected submission cleanup")
        await asyncio.sleep(0)
        assert not owner.done() and not closed.is_set()
        release.set()
        failure = await asyncio.wait_for(owner, 3)

        record = await journal.get("rejected-cancelled-cleanup")
        assert record is not None
        assert record.state is OperationState.FAILED, f"Queued record survived cancellation: {type(failure).__name__}"
        assert record.writers_stopped and record.ended_at is not None
        assert not record.processes and not reached_external_work
        assert await journal.unsettled() == []
        assert manager.get_task(record.operation_id) is None
        assert closed.is_set()
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
        assert isinstance(failure, RuntimeError)
        assert str(failure) == "后台任务管理器正在关闭"
        assert isinstance(failure.__cause__, asyncio.CancelledError)
    finally:
        release.set()
        await asyncio.gather(owner, return_exceptions=True)
        await generator.aclose()
