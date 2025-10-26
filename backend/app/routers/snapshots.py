"""Global snapshot management endpoints using restic"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from aiofiles import os as aioos
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..cron import restart_scheduler
from ..dependencies import get_current_user
from ..dynamic_config import config
from ..logger import logger
from ..minecraft import docker_mc_manager
from ..models import UserPublic
from ..snapshots import (
    ResticRestorePreviewAction,
    ResticSnapshot,
    ResticSnapshotWithSummary,
    restic_manager,
)
from ..system.resources import get_disk_info

router = APIRouter(
    prefix="/snapshots",
    tags=["snapshots"],
)


async def _check_backup_time_restriction():
    """
    Check if current time is in restricted backup periods.

    Raises HTTPException if current time is within configured seconds before/after
    the backup minutes defined by active backup cron jobs.
    """
    # Check if time restriction is enabled
    if not config.snapshots.time_restriction.enabled:
        return

    now = datetime.now()
    current_minute = now.minute
    current_second = now.second

    # Convert current time to total seconds from the start of the hour
    current_total_seconds = current_minute * 60 + current_second

    # Get backup minutes from active backup cron jobs
    backup_minutes = await restart_scheduler.get_backup_minutes()

    # If no backup jobs are configured, no restriction needed
    if not backup_minutes:
        return

    # Get configured restriction window
    before_seconds = config.snapshots.time_restriction.before_seconds
    after_seconds = config.snapshots.time_restriction.after_seconds

    # Convert minutes to seconds for comparison
    backup_marks_seconds = [minute * 60 for minute in backup_minutes]

    for mark_seconds in backup_marks_seconds:
        # Check if within restricted window:
        # From configured seconds before to configured seconds after the mark
        start_restriction = mark_seconds - before_seconds
        end_restriction = mark_seconds + after_seconds

        # Handle wrap-around for the 0-minute mark (going back to previous hour)
        if start_restriction < 0:
            # Check if in the wrap-around period (last X seconds of previous hour)
            if (
                current_total_seconds >= (3600 + start_restriction)
                or current_total_seconds <= end_restriction
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"请不要在备份时间({sorted(backup_minutes)})分的前{before_seconds}秒到后{after_seconds}秒尝试创建快照。",
                )
        else:
            # Normal case: check if current time is in the restricted window
            if start_restriction <= current_total_seconds <= end_restriction:
                raise HTTPException(
                    status_code=400,
                    detail=f"请不要在备份时间({sorted(backup_minutes)})分的前{before_seconds}秒到后{after_seconds}秒尝试创建快照。",
                )


def _get_restic_manager():
    """Get configured restic manager instance"""
    if not restic_manager:
        error_msg = (
            "Restic is not configured. Please add restic settings to config.toml"
        )
        logger.error(f"Snapshot operation failed: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=error_msg,
        )
    return restic_manager


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
        instance = docker_mc_manager.get_instance(server_id)
        return instance.get_project_path().resolve()
    elif server_id and path:
        # Backup specific path within server's data directory
        instance = docker_mc_manager.get_instance(server_id)
        data_path = instance.get_data_path()
        target_path = data_path / path.lstrip("/")
        return target_path.resolve()
    else:
        error_msg = "Cannot specify path without server_id"
        logger.error(
            f"Snapshot path resolution failed: {error_msg} (server_id={server_id}, path={path})"
        )
        raise HTTPException(status_code=400, detail=error_msg)


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
        # Check if current time is in restricted backup periods
        await _check_backup_time_restriction()

        backup_path = _resolve_backup_path(request.server_id, request.path)

        if not await aioos.path.exists(backup_path):
            error_msg = f"Path not found: {backup_path}"
            logger.error(
                f"Snapshot creation failed: {error_msg} (server_id={request.server_id}, path={request.path})"
            )
            raise HTTPException(status_code=404, detail=error_msg)

        restic_manager = _get_restic_manager()
        snapshot = await restic_manager.backup(backup_path)

        logger.info(
            f"Snapshot created successfully: {snapshot.short_id} for {backup_path} (server_id={request.server_id}, path={request.path})"
        )
        return CreateSnapshotResponse(
            message=f"Snapshot created successfully for {backup_path}",
            snapshot=snapshot,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to create snapshot: {str(e)}"
        logger.error(
            f"Snapshot creation error: {error_msg} (server_id={request.server_id}, path={request.path})",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=error_msg)


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

        logger.info(
            f"Listed {len(snapshots)} snapshots (server_id={server_id}, path={path})"
        )
        return ListSnapshotsResponse(snapshots=snapshots)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to list snapshots: {str(e)}"
        logger.error(
            f"Snapshot listing error: {error_msg} (server_id={server_id}, path={path})",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=error_msg)


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

        summary = f"预览结果：{updated_count} 个文件更新，{deleted_count} 个文件删除，{restored_count} 个文件恢复"

        logger.info(
            f"Restore preview completed for snapshot {request.snapshot_id}: {summary} (server_id={request.server_id}, path={request.path})"
        )
        return RestorePreviewResponse(actions=actions, preview_summary=summary)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to preview restore: {str(e)}"
        logger.error(
            f"Restore preview error: {error_msg} (snapshot_id={request.snapshot_id}, server_id={request.server_id}, path={request.path})",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/restore")
async def restore_global_snapshot(
    request: RestoreRequest, _: UserPublic = Depends(get_current_user)
):
    """Restore snapshot with automatic pre-restore backup"""
    try:
        target_path = _resolve_backup_path(request.server_id, request.path)

        restic_manager = _get_restic_manager()

        # Create a safety snapshot before restoring
        logger.info(
            f"Creating safety snapshot before restore (snapshot_id={request.snapshot_id}, server_id={request.server_id}, path={request.path})"
        )
        try:
            safety_snapshot = await restic_manager.backup(target_path)
            logger.info(
                f"Safety snapshot created: {safety_snapshot.short_id} before restoring to {target_path}"
            )
        except Exception as e:
            error_msg = f"Failed to create safety snapshot before restore: {str(e)}"
            logger.error(
                f"Safety snapshot creation failed: {error_msg} (snapshot_id={request.snapshot_id}, server_id={request.server_id}, path={request.path})",
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail=error_msg,
            )

        # Perform restore
        await restic_manager.restore(
            snapshot_id=request.snapshot_id,
            target_path=Path("/"),
            include_path=target_path,
        )

        success_msg = (
            f"Snapshot {request.snapshot_id} restored successfully to {target_path}"
        )
        logger.info(
            f"Restore completed: {success_msg} (safety_snapshot_id={safety_snapshot.short_id}, server_id={request.server_id}, path={request.path})"
        )
        return {
            "message": success_msg,
            "safety_snapshot_id": safety_snapshot.short_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to restore snapshot: {str(e)}"
        logger.error(
            f"Restore error: {error_msg} (snapshot_id={request.snapshot_id}, server_id={request.server_id}, path={request.path})",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.delete("/{snapshot_id}")
async def delete_snapshot(snapshot_id: str, _: UserPublic = Depends(get_current_user)):
    """Delete a specific snapshot by ID"""
    try:
        restic_manager = _get_restic_manager()

        # Delete the snapshot
        await restic_manager.forget_id(snapshot_id=snapshot_id, prune=True)

        success_msg = f"Snapshot {snapshot_id} deleted successfully"
        logger.info(f"Snapshot deleted: {snapshot_id}")
        return {"message": success_msg}

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to delete snapshot: {str(e)}"
        logger.error(
            f"Snapshot deletion error: {error_msg} (snapshot_id={snapshot_id})",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=error_msg)


# Backup repository disk usage models
class BackupRepositoryUsage(BaseModel):
    backupUsedGB: float
    backupTotalGB: float
    backupAvailableGB: float


@router.get("/repository-usage", response_model=BackupRepositoryUsage)
async def get_backup_repository_usage(_: UserPublic = Depends(get_current_user)):
    """Get backup repository disk usage information"""
    if not settings.restic or not settings.restic.repository_path:
        error_msg = (
            "Restic is not configured. Please add restic settings to config.toml"
        )
        logger.error(f"Repository usage query failed: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=error_msg,
        )

    repository_path = Path(settings.restic.repository_path)
    disk_info = await get_disk_info(repository_path)

    return BackupRepositoryUsage(
        backupUsedGB=disk_info.used / 1024**3,
        backupTotalGB=disk_info.total / 1024**3,
        backupAvailableGB=(disk_info.total - disk_info.used) / 1024**3,
    )


# Lock management models
class ListLocksResponse(BaseModel):
    locks: str


class UnlockResponse(BaseModel):
    message: str
    output: str


@router.get("/locks", response_model=ListLocksResponse)
async def list_locks(_: UserPublic = Depends(get_current_user)):
    """List all locks in the repository"""
    try:
        restic_manager = _get_restic_manager()
        locks_output = await restic_manager.list_locks()

        logger.info("Listed locks in repository")
        return ListLocksResponse(locks=locks_output)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to list locks: {str(e)}"
        logger.error(f"Lock listing error: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/unlock", response_model=UnlockResponse)
async def unlock_repository(_: UserPublic = Depends(get_current_user)):
    """Remove stale locks from the repository"""
    try:
        restic_manager = _get_restic_manager()
        unlock_output = await restic_manager.unlock()

        success_msg = "Repository unlocked successfully"
        logger.info("Repository unlocked")
        return UnlockResponse(message=success_msg, output=unlock_output)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to unlock repository: {str(e)}"
        logger.error(f"Unlock error: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)
