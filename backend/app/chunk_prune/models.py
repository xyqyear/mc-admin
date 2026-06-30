from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

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
    user_id: Optional[int] = None
    claims_file: Optional[Path] = None
    result: Optional[dict[str, Any]] = None
    geometry: Optional[ChunkPrunePreviewGeometryResponse] = None
    affected_regions_by_dimension: dict[str, set[tuple[int, int]]] = field(
        default_factory=dict
    )
