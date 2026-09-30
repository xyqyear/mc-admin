from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.snapshots import ResticRestoreAction, ResticSnapshot

from .restoration_models import RestorationStatus
from .scopes import SnapshotScope


class CreateSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: SnapshotScope


class RestorePreviewRequest(BaseModel):
    snapshot_id: str
    server_id: str | None = None
    paths: list[str] | None = None


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: SnapshotScope
    source_snapshot_id: str = Field(pattern="^[0-9a-f]{64}$")
    entry_point: Literal["files", "world", "snapshots"] = "files"


class SnapshotTaskAccepted(BaseModel):
    task_id: str
    restoration_id: str | None = None
    skipped_paths: list[str] = []


class RestorationResponse(BaseModel):
    id: str
    operation_id: str | None
    server_id: str | None
    scope: SnapshotScope | None
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


class RestorePreviewAction(BaseModel):
    action: ResticRestoreAction
    item: str | None = None
    size: int | None = None


class RestorePreviewResponse(BaseModel):
    actions: list[RestorePreviewAction]
    preview_summary: str


class BackupRepositoryUsage(BaseModel):
    backupUsedGB: float
    backupTotalGB: float
    backupAvailableGB: float


class ListLocksResponse(BaseModel):
    locks: str


class UnlockResponse(BaseModel):
    message: str
    output: str
