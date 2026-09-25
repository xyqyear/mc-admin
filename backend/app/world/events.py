from typing import Literal

from pydantic import BaseModel

from ..errors import PublicOperationError


class RestoreEvent(BaseModel):
    """SSE event emitted by ``begin_restore`` / ``rollback``."""

    event_type: Literal[
        "start",
        "safety_snapshot",
        "stage",
        "merge_region",
        "restore",
        "invalidate_cache",
        "complete",
        "error",
    ]
    message: str | None = None
    percent: float | None = None
    rx: int | None = None
    rz: int | None = None
    sub_dir: str | None = None
    restoration_id: str | None = None
    safety_snapshot_id: str | None = None


class PreviewEvent(BaseModel):
    """SSE event emitted by ``begin_preview``."""

    event_type: Literal[
        "start",
        "stage",
        "merge_region",
        "render_progress",
        "ready",
        "error",
    ]
    message: str | None = None
    session_id: str | None = None
    percent: float | None = None


class RestoreError(PublicOperationError):
    pass


class ServerNotStoppedError(RestoreError):
    """Raised when a restore is attempted while the target server is up."""


class SelectionResolutionError(RestoreError):
    """Raised when a selection cannot be resolved to filesystem paths."""
