import asyncio

import pytest

from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskProgress, TaskStatus, TaskType
from app.errors import PublicOperationError


@pytest.mark.parametrize("failed", [False, True])
async def test_snapshot_task_terminal_waits_for_owned_finalization(failed):
    cleaning, release = asyncio.Event(), asyncio.Event()
    manager = BackgroundTaskManager()

    async def restore():
        try:
            yield TaskProgress(message="已写入所选范围")
            if failed:
                raise PublicOperationError("恢复未完成")
            yield TaskProgress(progress=100, message="数据已恢复")
        finally:
            cleaning.set()
            await release.wait()

    accepted = manager.submit(TaskType.SNAPSHOT_RESTORE, "恢复快照", restore())
    try:
        await asyncio.wait_for(cleaning.wait(), 1)
        assert not accepted.awaitable.done()
        task = manager.get_task(accepted.task_id)
        assert task is not None and task.status is TaskStatus.RUNNING
        release.set()
        result = await asyncio.wait_for(accepted.awaitable, 1)
        assert result.success is not failed
        task = manager.get_task(accepted.task_id)
        assert task is not None and task.status is (
            TaskStatus.FAILED if failed else TaskStatus.COMPLETED
        )
    finally:
        release.set()
        await manager.shutdown()
