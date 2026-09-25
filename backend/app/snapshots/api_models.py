from pydantic import BaseModel

from app.snapshots import ResticRestoreAction, ResticSnapshot, ResticSnapshotWithSummary


class CreateSnapshotRequest(BaseModel):
    server_id: str | None = None
    paths: list[str] | None = None


class RestorePreviewRequest(BaseModel):
    snapshot_id: str
    server_id: str | None = None
    paths: list[str] | None = None


class RestoreRequest(BaseModel):
    snapshot_id: str
    server_id: str | None = None
    paths: list[str] | None = None


class CreateSnapshotResponse(BaseModel):
    message: str
    snapshot: ResticSnapshotWithSummary


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
