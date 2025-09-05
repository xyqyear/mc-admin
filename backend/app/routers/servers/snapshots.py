"""Snapshot management endpoints for Minecraft servers using restic"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager
from ...models import UserPublic
from ...snapshots import (
    ResticManager,
    ResticRestorePreviewAction,
    ResticSnapshot,
    ResticSnapshotWithSummary,
)

router = APIRouter(
    prefix="/servers",
    tags=["snapshots"],
)

mc_manager = DockerMCManager(settings.server_path)


def _get_restic_manager() -> ResticManager:
    """Get configured restic manager instance"""
    if not settings.restic:
        raise HTTPException(
            status_code=500,
            detail="Restic is not configured. Please add restic settings to config.toml",
        )
    return ResticManager(
        repository_path=settings.restic.repository_path,
        password=settings.restic.password,
    )


def _resolve_backup_path(server_id: Optional[str], path: Optional[str]) -> Path:
    """
    Resolve the actual backup path based on server_id and path parameters

    Args:
        server_id: Optional server identifier
        path: Optional path within server (relative to data directory)

    Returns:
        Absolute path to backup
    """
    if not server_id and not path:
        # Backup entire servers directory
        return settings.server_path.resolve()
    elif server_id and not path:
        # Backup specific server directory
        instance = mc_manager.get_instance(server_id)
        return instance.get_project_path().resolve()
    elif server_id and path:
        # Backup specific path within server's data directory
        instance = mc_manager.get_instance(server_id)
        data_path = instance.get_project_path() / "data"
        target_path = data_path / path.lstrip("/")
        return target_path.resolve()
    else:
        raise HTTPException(
            status_code=400, detail="Cannot specify path without server_id"
        )


# Request/Response models
class CreateSnapshotRequest(BaseModel):
    server_id: Optional[str] = None
    path: Optional[str] = None


class ListSnapshotsRequest(BaseModel):
    server_id: Optional[str] = None
    path: Optional[str] = None


class RestorePreviewRequest(BaseModel):
    snapshot_id: str
    server_id: Optional[str] = None
    path: Optional[str] = None


class RestoreRequest(BaseModel):
    snapshot_id: str
    server_id: Optional[str] = None
    path: Optional[str] = None


class CreateSnapshotResponse(BaseModel):
    message: str
    snapshot: ResticSnapshotWithSummary


class ListSnapshotsResponse(BaseModel):
    snapshots: List[ResticSnapshot]


class RestorePreviewResponse(BaseModel):
    actions: List[ResticRestorePreviewAction]
    preview_summary: str


# Endpoints
@router.post("/snapshots", response_model=CreateSnapshotResponse)
async def create_snapshot(
    request: CreateSnapshotRequest, _: UserPublic = Depends(get_current_user)
):
    """Create a snapshot of the specified server/path"""
    try:
        backup_path = _resolve_backup_path(request.server_id, request.path)

        if not backup_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Path not found: {backup_path}"
            )

        restic_manager = _get_restic_manager()
        snapshot = await restic_manager.backup(backup_path)

        return CreateSnapshotResponse(
            message=f"Snapshot created successfully for {backup_path}",
            snapshot=snapshot,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create snapshot: {str(e)}"
        )


@router.get("/snapshots", response_model=ListSnapshotsResponse)
async def list_snapshots(
    server_id: Optional[str] = None,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """List snapshots for the specified server/path"""
    try:
        restic_manager = _get_restic_manager()

        if server_id:
            filter_path = _resolve_backup_path(server_id, path)
        else:
            filter_path = None

        snapshots = await restic_manager.list_snapshots(path_filter=filter_path)

        return ListSnapshotsResponse(snapshots=snapshots)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list snapshots: {str(e)}"
        )


@router.post("/snapshots/restore/preview", response_model=RestorePreviewResponse)
async def preview_restore(
    request: RestorePreviewRequest, _: UserPublic = Depends(get_current_user)
):
    """Preview restore operation (dry run)"""
    try:
        target_path = _resolve_backup_path(request.server_id, request.path)

        restic_manager = _get_restic_manager()
        actions = await restic_manager.restore_preview(
            snapshot_id=request.snapshot_id,
            target_path=Path("/"),  # Restore in-place
            include_path=target_path,
        )

        # Create summary
        updated_count = sum(1 for a in actions if a.action == "updated")
        deleted_count = sum(1 for a in actions if a.action == "deleted")
        restored_count = sum(1 for a in actions if a.action == "restored")

        summary = f"Preview: {updated_count} updated, {deleted_count} deleted, {restored_count} restored"

        return RestorePreviewResponse(actions=actions, preview_summary=summary)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to preview restore: {str(e)}"
        )


@router.post("/snapshots/restore")
async def restore_snapshot(
    request: RestoreRequest, _: UserPublic = Depends(get_current_user)
):
    """Restore snapshot with safety checks"""
    try:
        target_path = _resolve_backup_path(request.server_id, request.path)

        restic_manager = _get_restic_manager()

        # Safety check: Ensure there's a recent snapshot (within 1 minute)
        has_recent = await restic_manager.has_recent_snapshot(
            target_path=target_path, max_age_seconds=60
        )

        if not has_recent:
            raise HTTPException(
                status_code=400,
                detail="No recent snapshot found. Create a snapshot within 1 minute before restoring to prevent data loss.",
            )

        # Perform restore
        await restic_manager.restore(
            snapshot_id=request.snapshot_id,
            target_path=Path("/"),
            include_path=target_path,
        )

        return {
            "message": f"Snapshot {request.snapshot_id} restored successfully to {target_path}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to restore snapshot: {str(e)}"
        )


# Specific server snapshot endpoints
@router.post("/{server_id}/snapshots", response_model=CreateSnapshotResponse)
async def create_server_snapshot(
    server_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Create snapshot for specific server"""
    request = CreateSnapshotRequest(server_id=server_id, path=path)
    return await create_snapshot(request, _)


@router.get("/{server_id}/snapshots", response_model=ListSnapshotsResponse)
async def list_server_snapshots(
    server_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """List snapshots for specific server"""
    return await list_snapshots(server_id=server_id, path=path, _=_)


@router.post(
    "/{server_id}/snapshots/restore/preview", response_model=RestorePreviewResponse
)
async def preview_server_restore(
    server_id: str,
    snapshot_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Preview restore for specific server"""
    request = RestorePreviewRequest(
        snapshot_id=snapshot_id, server_id=server_id, path=path
    )
    return await preview_restore(request, _)


@router.post("/{server_id}/snapshots/restore")
async def restore_server_snapshot(
    server_id: str,
    snapshot_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Restore snapshot for specific server"""
    request = RestoreRequest(snapshot_id=snapshot_id, server_id=server_id, path=path)
    return await restore_snapshot(request, _)
