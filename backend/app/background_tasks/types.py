from enum import Enum
from typing import Any

from pydantic import BaseModel


class TaskType(str, Enum):
    ARCHIVE_CREATE = "archive_create"
    ARCHIVE_EXTRACT = "archive_extract"
    SNAPSHOT_CREATE = "snapshot_create"
    SNAPSHOT_RESTORE = "snapshot_restore"
    SERVER_START = "server_start"
    SERVER_STOP = "server_stop"
    SERVER_RESTART = "server_restart"


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
