from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..background_tasks import task_manager
from ..background_tasks.models import BackgroundTask
from ..background_tasks.types import TaskStatus, TaskType

router = APIRouter(prefix="/tasks", tags=["tasks"])


class BackgroundTaskResponse(BaseModel):
    """API response model for a background task."""

    task_id: str
    task_type: TaskType
    name: str
    status: TaskStatus
    progress: float | None
    message: str
    server_id: str | None
    cancellable: bool
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    result: dict[str, Any] | None
    error: str | None

    @classmethod
    def from_task(cls, task: BackgroundTask) -> "BackgroundTaskResponse":
        return cls(
            task_id=task.task_id,
            task_type=task.task_type,
            name=task.name,
            status=task.status,
            progress=task.progress,
            message=task.message,
            server_id=task.server_id,
            cancellable=task.cancellable,
            created_at=task.created_at,
            started_at=task.started_at,
            ended_at=task.ended_at,
            result=task.result,
            error=task.error,
        )


class BackgroundTaskListResponse(BaseModel):
    """API response model for a list of background tasks."""

    tasks: list[BackgroundTaskResponse]
    total: int


@router.get("", response_model=BackgroundTaskListResponse)
async def get_tasks(
    active_only: bool = False,
    server_id: str | None = None,
    status: str | None = None,
):
    """Get task list with optional filtering."""
    tasks = (
        task_manager.get_active_tasks() if active_only else task_manager.get_all_tasks()
    )

    if server_id is not None:
        tasks = [t for t in tasks if t.server_id == server_id]
    if status:
        tasks = [t for t in tasks if t.status.value == status]

    return BackgroundTaskListResponse(
        tasks=[BackgroundTaskResponse.from_task(t) for t in tasks],
        total=len(tasks),
    )


@router.get("/{task_id}", response_model=BackgroundTaskResponse)
async def get_task(task_id: str):
    """Get a single task by ID."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return BackgroundTaskResponse.from_task(task)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a running task."""
    success = await task_manager.cancel(task_id)
    if not success:
        raise HTTPException(400, "Cannot cancel task")
    return {"success": True}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a completed task."""
    success = task_manager.remove_task(task_id)
    if not success:
        raise HTTPException(400, "Cannot delete task (still running or not found)")
    return {"success": True}


@router.delete("")
async def clear_completed(completed_only: bool = True):
    """Clear completed/failed/cancelled tasks."""
    count = task_manager.clear_completed()
    return {"cleared": count}
