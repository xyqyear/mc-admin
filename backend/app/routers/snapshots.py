"""Global snapshot management endpoints using restic"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..dependencies import get_current_user
from ..logger import logger
from ..minecraft import DockerMCManager
from ..models import UserPublic
from ..snapshots import (
    ResticManager,
    ResticRestorePreviewAction,
    ResticSnapshot,
    ResticSnapshotWithSummary,
)

router = APIRouter(
    prefix="/snapshots",
    tags=["snapshots"],
)

mc_manager = DockerMCManager(settings.server_path)


def _get_restic_manager() -> ResticManager:
    """Get configured restic manager instance"""
    if not settings.restic:
        error_msg = "Restic is not configured. Please add restic settings to config.toml"
        logger.error(f"Snapshot operation failed: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=error_msg,
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
        error_msg = "Cannot specify path without server_id"
        logger.error(f"Snapshot path resolution failed: {error_msg} (server_id={server_id}, path={path})")
        raise HTTPException(
            status_code=400, detail=error_msg
        )


# Request/Response models
class CreateSnapshotRequest(BaseModel):
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


# Global snapshot endpoints
@router.post("", response_model=CreateSnapshotResponse)
async def create_global_snapshot(
    request: CreateSnapshotRequest, _: UserPublic = Depends(get_current_user)
):
    """Create a global snapshot or snapshot of the specified server/path"""
    try:
        backup_path = _resolve_backup_path(request.server_id, request.path)

        if not backup_path.exists():
            error_msg = f"Path not found: {backup_path}"
            logger.error(f"Snapshot creation failed: {error_msg} (server_id={request.server_id}, path={request.path})")
            raise HTTPException(
                status_code=404, detail=error_msg
            )

        restic_manager = _get_restic_manager()
        snapshot = await restic_manager.backup(backup_path)

        logger.info(f"Snapshot created successfully: {snapshot.short_id} for {backup_path} (server_id={request.server_id}, path={request.path})")
        return CreateSnapshotResponse(
            message=f"Snapshot created successfully for {backup_path}",
            snapshot=snapshot,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to create snapshot: {str(e)}"
        logger.error(f"Snapshot creation error: {error_msg} (server_id={request.server_id}, path={request.path})", exc_info=True)
        raise HTTPException(
            status_code=500, detail=error_msg
        )


@router.get("", response_model=ListSnapshotsResponse)
async def list_global_snapshots(
    server_id: Optional[str] = None,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """List all snapshots or snapshots for the specified server/path"""
    try:
        restic_manager = _get_restic_manager()

        if server_id:
            filter_path = _resolve_backup_path(server_id, path)
        else:
            filter_path = None

        snapshots = await restic_manager.list_snapshots(path_filter=filter_path)

        logger.info(f"Listed {len(snapshots)} snapshots (server_id={server_id}, path={path})")
        return ListSnapshotsResponse(snapshots=snapshots)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to list snapshots: {str(e)}"
        logger.error(f"Snapshot listing error: {error_msg} (server_id={server_id}, path={path})", exc_info=True)
        raise HTTPException(
            status_code=500, detail=error_msg
        )


@router.post("/restore/preview", response_model=RestorePreviewResponse)
async def preview_global_restore(
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

        logger.info(f"Restore preview completed for snapshot {request.snapshot_id}: {summary} (server_id={request.server_id}, path={request.path})")
        return RestorePreviewResponse(actions=actions, preview_summary=summary)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to preview restore: {str(e)}"
        logger.error(f"Restore preview error: {error_msg} (snapshot_id={request.snapshot_id}, server_id={request.server_id}, path={request.path})", exc_info=True)
        raise HTTPException(
            status_code=500, detail=error_msg
        )


@router.post("/restore")
async def restore_global_snapshot(
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
            error_msg = "No recent snapshot found. Create a snapshot within 1 minute before restoring to prevent data loss."
            logger.warning(f"Restore blocked due to safety check: {error_msg} (snapshot_id={request.snapshot_id}, server_id={request.server_id}, path={request.path})")
            raise HTTPException(
                status_code=400,
                detail=error_msg,
            )

        # Perform restore
        await restic_manager.restore(
            snapshot_id=request.snapshot_id,
            target_path=Path("/"),
            include_path=target_path,
        )

        success_msg = f"Snapshot {request.snapshot_id} restored successfully to {target_path}"
        logger.info(f"Restore completed: {success_msg} (server_id={request.server_id}, path={request.path})")
        return {
            "message": success_msg
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to restore snapshot: {str(e)}"
        logger.error(f"Restore error: {error_msg} (snapshot_id={request.snapshot_id}, server_id={request.server_id}, path={request.path})", exc_info=True)
        raise HTTPException(
            status_code=500, detail=error_msg
        )
