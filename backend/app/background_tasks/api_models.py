from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel

from app.background_tasks.models import BackgroundTask
from app.background_tasks.types import TaskStatus, TaskType


class TaskAccepted(BaseModel):
    task_id: str


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
    def from_task(cls, task: BackgroundTask) -> Self:
        return cls.model_validate(task, from_attributes=True)


class BackgroundTaskResponse(BackgroundTaskSummaryResponse):
    """API response model for a background task."""

    result: dict[str, Any] | None


class BackgroundTaskListResponse(BaseModel):
    """API response model for a list of background tasks."""

    tasks: list[BackgroundTaskSummaryResponse]
    total: int
