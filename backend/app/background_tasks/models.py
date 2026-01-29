import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .types import TaskStatus, TaskType


class BackgroundTask(BaseModel):
    """Runtime representation of a background task."""

    model_config = {"arbitrary_types_allowed": True}

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType
    name: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float | None = None
    message: str = ""
    server_id: str | None = None
    cancellable: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    cancel_requested: bool = Field(default=False, exclude=True)
