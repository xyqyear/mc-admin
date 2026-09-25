from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..background_tasks.models import BackgroundTask
from ..servers.references import ServerRef
from .inputs import PruneInputVersion

PruneMode = Literal["chunks", "regions"]
PruneOperation = Literal["preview", "apply"]


class ChunkPruneSettingsResponse(BaseModel):
    default_threshold_seconds: int


class ChunkPrunePreviewRequest(BaseModel):
    threshold_seconds: int = Field(ge=0)
    mode: PruneMode = "regions"


class ChunkPruneStartResponse(BaseModel):
    task_id: str


GridGeometryUnit = Literal["chunk", "region"]


class GridShape(BaseModel):
    id: str
    cell_count: int
    bbox: tuple[int, int, int, int]
    rings: list[list[tuple[int, int]]]


class GridGeometryDimension(BaseModel):
    region_dir_relpath: str
    unit: GridGeometryUnit
    cell_count: int
    shapes: list[GridShape] = Field(default_factory=list)


class ChunkPrunePreviewGeometryResponse(BaseModel):
    task_id: str
    server_id: str
    mode: PruneMode
    threshold_seconds: int
    threshold_ticks: int
    dimensions: list[GridGeometryDimension] = Field(default_factory=list)


@dataclass
class ChunkPruneTaskMetadata:
    task_id: str
    server_id: str
    operation: PruneOperation
    data_path: Path
    threshold_seconds: int
    threshold_ticks: int
    mode: PruneMode
    user_id: int | None = None
    reference: ServerRef | None = None
    inputs: PruneInputVersion | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    apply_task_id: str | None = None
    preview_task_id: str | None = None
    references: int = 0
    unavailable_reason: str | None = None
    task: BackgroundTask | None = None
    claims_file: Path | None = None
    result: dict[str, Any] | None = None
    geometry: ChunkPrunePreviewGeometryResponse | None = None
    affected_regions_by_dimension: dict[str, set[tuple[int, int]]] = field(
        default_factory=dict
    )


class ChunkPrunePreviewState(BaseModel):
    task_id: str
    input_version: str | None = None
    expires_at: datetime | None = None
    availability: Literal["building", "ready", "expired", "stale", "consumed", "unavailable"]
    apply_task_id: str | None = None
