
from fastapi import APIRouter, Depends, HTTPException

from app.background_tasks.api_models import (
    BackgroundTaskListResponse,
    BackgroundTaskResponse,
    BackgroundTaskSummaryResponse,
)

from ..background_tasks import get_task_manager
from ..dependencies import get_current_user

router = APIRouter(
    prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=BackgroundTaskListResponse)
async def get_tasks(
    active_only: bool = False,
    server_id: str | None = None,
    status: str | None = None,
):
    """Get task list with optional filtering."""
    tasks = (
        get_task_manager().get_active_tasks() if active_only else get_task_manager().get_all_tasks()
    )

    if server_id is not None:
        tasks = [t for t in tasks if t.server_id == server_id]
    if status:
        tasks = [t for t in tasks if t.status.value == status]

    return BackgroundTaskListResponse(
        tasks=[BackgroundTaskSummaryResponse.from_task(t) for t in tasks],
        total=len(tasks),
    )


@router.get("/{task_id}", response_model=BackgroundTaskResponse)
async def get_task(task_id: str):
    """Get a single task by ID."""
    task = get_task_manager().get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return BackgroundTaskResponse.from_task(task)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a running task."""
    success = await get_task_manager().cancel(task_id)
    if not success:
        raise HTTPException(400, "Cannot cancel task")
    return {"success": True}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a completed task."""
    success = get_task_manager().remove_task(task_id)
    if not success:
        raise HTTPException(400, "Cannot delete task (still running or not found)")
    return {"success": True}


@router.delete("")
async def clear_completed(completed_only: bool = True):
    """Clear completed/failed/cancelled tasks."""
    count = get_task_manager().clear_completed()
    return {"cleared": count}
