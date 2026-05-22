"""Pydantic models for the mcmap module."""

from typing import Literal, Optional

from pydantic import BaseModel


class MapStatus(BaseModel):
    """Per-server map initialization state."""

    client_jar_present: bool
    palette_present: bool
    palette_current: bool
    version: Optional[str] = None


class InitEvent(BaseModel):
    """A single SSE event emitted by /initialize."""

    stage: Literal["client", "palette", "complete"]
    phase: Optional[
        Literal[
            "starting",
            "downloading",
            "verifying",
            "pack_loaded",
            "resolving",
            "done",
            "error",
        ]
    ] = None
    percent: Optional[float] = None
    message: Optional[str] = None
    cached: Optional[bool] = None


class MCMapError(Exception):
    """Raised when mcmap reports a failure (render, replace, remove, ...)."""
