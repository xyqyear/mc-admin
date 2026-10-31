import asyncio

from app.background_tasks import TaskType
from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskStatus
from app.mcmap import initialization
from app.mcmap.types import InitEvent


async def test_stage_snapshots_do_not_complete_task_before_initialization_settles(monkeypatch):
    finalizing, release = asyncio.Event(), asyncio.Event()

    async def events(*args, **kwargs):
        yield InitEvent(stage="client", phase="done", percent=100)
        yield InitEvent(stage="palette", phase="pack_loaded", percent=20)
        yield InitEvent(stage="palette", phase="done", percent=100)
        finalizing.set()
        await release.wait()
        yield InitEvent(stage="complete")

    monkeypatch.setattr(initialization, "initialize_events", events)
    manager = BackgroundTaskManager()
    try:
        submitted = manager.submit(
            TaskType.MAP_INITIALIZE, "地图初始化", initialization.initialize_task("alpha", False, 1),
        )
        await asyncio.wait_for(finalizing.wait(), 2)
        task = manager.get_task(submitted.task_id)
        assert task is not None and task.status is TaskStatus.RUNNING
        assert not submitted.awaitable.done() and task.result is None
        assert task.progress_details is not None
        assert task.progress_details["stages"]["client"]["phase"] == "done"
        assert task.progress_details["stages"]["palette"]["phase"] == "done"
        release.set()
        terminal = await asyncio.wait_for(submitted.awaitable, 2)
        assert terminal.success and terminal.data is not None
        assert terminal.data["stages"]["palette"]["phase"] == "done"
    finally:
        release.set()
        await manager.shutdown()
