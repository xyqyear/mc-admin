"""Pydantic models for the mcmap module."""

from typing import Literal

from pydantic import BaseModel


class MapStatus(BaseModel):
    """Per-server map initialization state."""

    client_jar_present: bool
    palette_present: bool
    palette_current: bool
    version: str | None = None


class InitEvent(BaseModel):
    """A single SSE event emitted by /initialize."""

    stage: Literal["client", "palette", "complete"]
    phase: Literal["starting", "downloading", "verifying", "pack_loaded", "resolving", "done", "error"] | None = None
    percent: float | None = None
    message: str | None = None
    cached: bool | None = None


class MCMapError(Exception):
    """Raised when mcmap reports a failure (render, replace, remove, ...)."""
