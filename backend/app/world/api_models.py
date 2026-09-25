from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.snapshots import ResticSnapshot, ResticSnapshotWithSummary
from app.world.models import RestorationStatus, RestorationType
from app.world.schemas import RestorationSelection


class DimensionInfoResponse(BaseModel):
    region_dir: str
    entities_dir: str | None = None
    poi_dir: str | None = None


class WorldRootResponse(BaseModel):
    name: str
    path: str
    dimensions: list[DimensionInfoResponse]


class WorldLayoutResponse(BaseModel):
    world_roots: list[WorldRootResponse]


class DimensionLabelsResponse(BaseModel):
    dimension_labels: dict[str, str]


class ListEligibleSnapshotsResponse(BaseModel):
    snapshots: list[ResticSnapshot]


class CreateSnapshotResponse(BaseModel):
    message: str
    snapshot: ResticSnapshotWithSummary


class ManualSnapshotRequest(BaseModel):
    # Region/chunk snapshots are only created automatically as safety snapshots.
    type: Literal["world", "dimension"]
    region_dir_relpath: str | None = None


class PreviewRequest(BaseModel):
    source_snapshot_id: str
    selection: RestorationSelection


class RestoreRequest(BaseModel):
    source_snapshot_id: str
    selection: RestorationSelection


class RestorationResponse(BaseModel):
    id: str
    server_id: str
    server_generation: int | None = None
    binding_issue: str | None = None
    type: RestorationType
    source_snapshot_id: str
    safety_snapshot_id: str | None
    source_snapshot_exists: bool
    safety_snapshot_exists: bool
    selection: RestorationSelection
    is_rollback: bool
    initiated_by_user_id: int | None
    started_at: datetime
    finished_at: datetime | None
    status: RestorationStatus
    error_message: str | None


class ListRestorationsResponse(BaseModel):
    restorations: list[RestorationResponse]
    total: int
