from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.snapshots import ResticSnapshot

from .restoration_models import RestorationStatus
from .scopes import SnapshotScope, WorldScope


class CreateSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: SnapshotScope
    note: str = Field(default="", max_length=500)


class UpdateSnapshotNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(max_length=500)


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: SnapshotScope
    source_snapshot_id: str = Field(pattern="^[0-9a-f]{64}$")
    entry_point: Literal["files", "world", "snapshots"] = "files"
    preview_id: str | None = Field(default=None, pattern="^[0-9a-f]{32}$")


class SnapshotTaskAccepted(BaseModel):
    task_id: str
    restoration_id: str | None = None
    skipped_paths: list[str] = []


class SnapshotTargetCheck(BaseModel):
    allowed: bool
    reason: str | None = None
    skipped_paths: list[str] = []
    skipped_count: int = 0


class CheckWorldSnapshotTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: WorldScope


class SnapshotTargetRules(BaseModel):
    server_id: str
    server_generation: int
    ignored_paths: list[str]
    rules_version: str


class RestorationTarget(BaseModel):
    server_id: str
    generation: int | None


class ActiveRestoration(BaseModel):
    id: str
    operation_id: str
    scope: SnapshotScope | None
    status: RestorationStatus


class ActiveRestorationsResponse(BaseModel):
    restorations: list[ActiveRestoration]
    total: int


class RestorationResponse(BaseModel):
    id: str
    operation_id: str | None
    server_id: str | None
    server_generation: int | None
    binding_issue: str | None
    entry_point: str | None
    initiated_by_user_id: int | None
    scope: SnapshotScope | None
    targets: list[RestorationTarget]
    source_snapshot_id: str
    safety_snapshot_id: str | None
    source_snapshot_exists: bool
    safety_snapshot_exists: bool
    rollback_available: bool
    rollback_unavailable_reason: str | None
    rollback_of_id: str | None
    is_rollback: bool
    started_at: datetime
    finished_at: datetime | None
    status: RestorationStatus
    error_message: str | None


class ListRestorationsResponse(BaseModel):
    restorations: list[RestorationResponse]
    total: int


class ListSnapshotsResponse(BaseModel):
    snapshots: list[ResticSnapshot]


class BackupRepositoryUsage(BaseModel):
    backupUsedGB: float
    backupTotalGB: float
    backupAvailableGB: float


class ListLocksResponse(BaseModel):
    locks: str
