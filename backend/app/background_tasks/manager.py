import asyncio
from datetime import datetime
from typing import AsyncGenerator

from pydantic import BaseModel

from ..logger import logger
from .models import BackgroundTask
from .types import TaskProgress, TaskResult, TaskStatus, TaskType


class SubmitResult(BaseModel):
    """Result returned when submitting a task."""

    model_config = {"arbitrary_types_allowed": True}

    task_id: str
    task: BackgroundTask
    awaitable: asyncio.Future[TaskResult]


class BackgroundTaskManager:
    """Manager for background tasks. Singleton instance."""

    def __init__(self):
        self._tasks: dict[str, BackgroundTask] = {}
        self._asyncio_tasks: dict[str, asyncio.Task] = {}
        self._futures: dict[str, asyncio.Future[TaskResult]] = {}

    def submit(
        self,
        task_type: TaskType,
        name: str,
        task_generator: AsyncGenerator[TaskProgress, None],
        server_id: str | None = None,
        cancellable: bool = True,
    ) -> SubmitResult:
        """
        Submit a background task.

        Args:
            task_type: Type of the task
            name: Display name for the task
            task_generator: Instantiated async generator that yields TaskProgress
            server_id: Associated server ID, or None for global tasks
            cancellable: Whether the task can be cancelled

        Returns:
            SubmitResult containing task_id and an awaitable Future

        Example:
            async def compress_task(path: str):
                for i in range(100):
                    yield TaskProgress(progress=i, message=f"Processing {i}%")
                yield TaskProgress(progress=100, message="Done", result={"size": 1024})

            result = manager.submit(
                TaskType.ARCHIVE_CREATE,
                "backup.7z",
                compress_task("/data"),
                server_id="survival"
            )
            # Immediate return
            return {"task_id": result.task_id}

            # Or wait for completion
            task_result = await result.awaitable
        """
        task = BackgroundTask(
            task_type=task_type,
            name=name,
            server_id=server_id,
            cancellable=cancellable,
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[TaskResult] = loop.create_future()

        self._tasks[task.task_id] = task
        self._futures[task.task_id] = future

        async def run_task():
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()

            try:
                async for progress in task_generator:
                    if task.cancel_requested:
                        task.status = TaskStatus.CANCELLED
                        task.ended_at = datetime.now()
                        task.message = "已取消"
                        future.set_result(TaskResult(success=False, error="已取消"))
                        logger.info(
                            f"Task {task.task_id} ({task.name}) cancelled by user"
                        )
                        return

                    task.progress = progress.progress
                    task.message = progress.message
                    if progress.result is not None:
                        task.result = progress.result

                task.status = TaskStatus.COMPLETED
                task.ended_at = datetime.now()
                if task.progress is not None:
                    task.progress = 100
                future.set_result(TaskResult(success=True, data=task.result))
                logger.info(f"Task {task.task_id} ({task.name}) completed successfully")

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.ended_at = datetime.now()
                task.error = str(e)
                future.set_result(TaskResult(success=False, error=str(e)))
                logger.exception(f"Task {task.task_id} ({task.name}) failed: {e}")

        asyncio_task = asyncio.create_task(run_task())
        self._asyncio_tasks[task.task_id] = asyncio_task
        logger.info(
            f"Task {task.task_id} ({task.name}) submitted, type={task_type.value}, server_id={server_id}"
        )

        return SubmitResult(task_id=task.task_id, task=task, awaitable=future)

    async def cancel(self, task_id: str) -> bool:
        """Request cancellation of a task."""
        task = self._tasks.get(task_id)
        if not task or not task.cancellable:
            return False
        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        task.cancel_requested = True
        logger.info(f"Cancel requested for task {task_id} ({task.name})")
        return True

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[BackgroundTask]:
        """Get all tasks."""
        return list(self._tasks.values())

    def get_active_tasks(self) -> list[BackgroundTask]:
        """Get pending and running tasks."""
        return [
            t
            for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]

    def remove_task(self, task_id: str) -> bool:
        """Remove a completed task."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        del self._tasks[task_id]
        self._asyncio_tasks.pop(task_id, None)
        self._futures.pop(task_id, None)
        return True

    def clear_completed(self) -> int:
        """Clear all completed/failed/cancelled tasks."""
        to_remove = [
            tid
            for tid, t in self._tasks.items()
            if t.status not in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]
        for tid in to_remove:
            del self._tasks[tid]
            self._asyncio_tasks.pop(tid, None)
            self._futures.pop(tid, None)
        return len(to_remove)


task_manager = BackgroundTaskManager()
