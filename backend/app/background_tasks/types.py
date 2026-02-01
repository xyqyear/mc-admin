from enum import Enum
from typing import Any

from pydantic import BaseModel


class TaskType(str, Enum):
    ARCHIVE_CREATE = "archive_create"
    ARCHIVE_EXTRACT = "archive_extract"
    SERVER_REBUILD = "server_rebuild"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskProgress(BaseModel):
    """Progress information yielded by task functions."""

    progress: float | None = None
    message: str = ""
    result: dict[str, Any] | None = None


class TaskResult(BaseModel):
    """Result returned when a task completes."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
