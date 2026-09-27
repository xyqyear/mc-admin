from enum import Enum
from typing import Any

from pydantic import BaseModel


class TaskType(str, Enum):
    SERVER_START = "server_start"
    SERVER_UP = "server_up"
    SERVER_RESTART = "server_restart"
    SERVER_STOP = "server_stop"
    SERVER_DOWN = "server_down"
    SERVER_REMOVE = "server_remove"
    SERVER_CREATE = "server_create"
    SERVER_SYNC = "server_sync"
    FILE_DELETE = "file_delete"
    ARCHIVE_DELETE = "archive_delete"
    MAP_INITIALIZE = "map_initialize"
    SELF_CHECK = "self_check"
    DNS_UPDATE = "dns_update"
    ARCHIVE_HASH = "archive_hash"
    ARCHIVE_PUBLISH = "archive_publish"
    ARCHIVE_CREATE = "archive_create"
    ARCHIVE_EXTRACT = "archive_extract"
    FILE_OWNERSHIP_REPAIR = "file_ownership_repair"
    SERVER_REBUILD = "server_rebuild"
    WORLD_RESTORE = "world_restore"
    CHUNK_PRUNE_PREVIEW = "chunk_prune_preview"
    CHUNK_PRUNE_APPLY = "chunk_prune_apply"


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
