from typing import Literal

from pydantic import BaseModel

from ..errors import PublicOperationError


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


class SelectionResolutionError(RestoreError):
    """Raised when a selection cannot be resolved to filesystem paths."""
