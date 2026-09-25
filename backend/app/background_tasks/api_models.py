from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.background_tasks.models import BackgroundTask
from app.background_tasks.types import TaskStatus, TaskType


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
    error_code: str | None = None

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
            error_code=task.error_code,
        )


class BackgroundTaskSummaryResponse(BaseModel):
    """Lightweight API response model for task lists."""

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
    error: str | None
    error_code: str | None = None

    @classmethod
    def from_task(cls, task: BackgroundTask) -> "BackgroundTaskSummaryResponse":
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
            error=task.error,
            error_code=task.error_code,
        )


class BackgroundTaskListResponse(BaseModel):
    """API response model for a list of background tasks."""

    tasks: list[BackgroundTaskSummaryResponse]
    total: int
