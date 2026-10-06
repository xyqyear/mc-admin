"""Pydantic models for the mcmap module."""

from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel


class RenderCache(Protocol):
    @property
    def data_path(self) -> Path: ...

    @property
    def palette_json(self) -> Path: ...

    def mca_path(self, region_path: str, x: int, z: int, /) -> Path: ...

    def tiles_dir(self, region_path: str, /) -> Path: ...

    def png_path(self, region_path: str, x: int, z: int, /) -> Path: ...

    async def ensure_dir(self, target: Path) -> None: ...


class MapStatus(BaseModel):
    """Per-server map initialization state."""

    client_jar_present: bool
    palette_present: bool
    palette_current: bool
    version: str | None = None


class InitEvent(BaseModel):
    """Progress for one stage of map initialization."""

    stage: Literal["client", "palette", "complete"]
    phase: Literal["starting", "downloading", "verifying", "pack_loaded", "resolving", "done", "error"] | None = None
    percent: float | None = None
    message: str | None = None
    cached: bool | None = None


class MCMapError(Exception):
    """Raised when mcmap reports a failure (render, replace, remove, ...)."""
