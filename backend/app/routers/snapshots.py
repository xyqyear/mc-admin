"""Global snapshot management endpoints using restic"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.schemas import UserPublic
from app.snapshots.api_models import (
    BackupRepositoryUsage,
    CreateSnapshotRequest,
    ListLocksResponse,
    ListRestorationsResponse,
    ListSnapshotsResponse,
    RestorationResponse,
    RestorePreviewAction,
    RestorePreviewRequest,
    RestorePreviewResponse,
    RestoreRequest,
    SnapshotTaskAccepted,
    UnlockResponse,
)

from ..config import get_settings
from ..cron import get_restart_scheduler
from ..db.database import get_session_factory
from ..dependencies import get_current_user
from ..dynamic_config import get_config
from ..logger import get_logger
from ..minecraft import get_docker_mc_manager
from ..snapshots import (
    TargetIgnoredError,
    get_snapshot_service,
)
from ..snapshots.application import resolve_backup_paths
from ..snapshots.commands import get_snapshot_commands
from ..snapshots.file_restore import (
    SnapshotMaintenanceConflict,
    SnapshotServerRunning,
)
from ..snapshots.policy import check_backup_time_restriction
from ..snapshots.queries import RestorationQueries
from ..system.resources import get_disk_info

router = APIRouter(
    prefix="/snapshots",
    tags=["snapshots"],
)


async def _check_backup_time_restriction():
    if get_config().snapshots.time_restriction.enabled:
        await check_backup_time_restriction(get_config().snapshots.time_restriction, await get_restart_scheduler().get_backup_minutes(), datetime.now(UTC).astimezone())


def _get_snapshot_service():
    snapshot_service = get_snapshot_service()
    if not snapshot_service:
        raise HTTPException(
            status_code=500,
            detail="Restic is not configured. Please add restic settings to config.toml",
        )
    return snapshot_service


async def _resolve_backup_paths(
    server_id: str | None, paths: list[str] | None
) -> list[Path]:
    settings = get_settings()
    return await resolve_backup_paths(get_docker_mc_manager(), Path(settings.server_path), server_id, paths)




def _commands():
    commands = get_snapshot_commands()
    if commands is None:
        raise HTTPException(status_code=500, detail="尚未配置快照仓库")
    return commands


@router.post("", status_code=202, response_model=SnapshotTaskAccepted)
async def create_global_snapshot(request: CreateSnapshotRequest, user: UserPublic = Depends(get_current_user)):
    await _check_backup_time_restriction()
    try:
        return await _commands().create(request.scope, user.id)
    except TargetIgnoredError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("", response_model=ListSnapshotsResponse)
async def list_global_snapshots(
    server_id: str | None = None,
    path: str | None = None,
    _: UserPublic = Depends(get_current_user),
):
    """List all snapshots, or snapshots that touch the specified server/path"""
    service = _get_snapshot_service()

    if server_id:
        resolved = await _resolve_backup_paths(
            server_id, [path] if path else None
        )
        filter_path = resolved[0]
    else:
        filter_path = None

    snapshots = await service.list_snapshots(path_filter=filter_path)
    return ListSnapshotsResponse(snapshots=snapshots)


@router.post("/restore/preview", response_model=RestorePreviewResponse)
async def preview_global_restore(
    request: RestorePreviewRequest, _: UserPublic = Depends(get_current_user)
):
    """Preview restore operation (dry run)"""
    target_paths = await _resolve_backup_paths(request.server_id, request.paths)

    service = _get_snapshot_service()
    try:
        events = await service.preview(request.snapshot_id, target_paths)
    except TargetIgnoredError as e:
        raise HTTPException(status_code=400, detail=str(e))

    actions = [
        RestorePreviewAction(action=ev.action, item=ev.item, size=ev.size)
        for ev in events
        if ev.action is not None
    ]

    updated_count = sum(1 for a in actions if a.action == "updated")
    deleted_count = sum(1 for a in actions if a.action == "deleted")
    restored_count = sum(1 for a in actions if a.action == "restored")

    summary = f"预览结果：{updated_count} 个文件更新，{deleted_count} 个文件删除，{restored_count} 个文件恢复"
    return RestorePreviewResponse(actions=actions, preview_summary=summary)


@router.post("/restorations", status_code=202, response_model=SnapshotTaskAccepted)
async def restore_snapshot(request: RestoreRequest, user: UserPublic = Depends(get_current_user)):
    try:
        return await _commands().restore(request.scope, request.source_snapshot_id, user.id, entry_point=request.entry_point)
    except SnapshotMaintenanceConflict as error:
        raise HTTPException(status_code=423, detail=str(error)) from error
    except SnapshotServerRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TargetIgnoredError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/restorations", response_model=ListRestorationsResponse)
async def list_restorations(
    server_id: str | None = None, limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0), _: UserPublic = Depends(get_current_user),
):
    return await RestorationQueries(get_session_factory(), _get_snapshot_service()).history(server_id, limit, offset)


@router.get("/restorations/{restoration_id}", response_model=RestorationResponse)
async def get_restoration(restoration_id: str, _: UserPublic = Depends(get_current_user)):
    return await RestorationQueries(get_session_factory(), _get_snapshot_service()).get(restoration_id)


@router.post("/restorations/{restoration_id}/rollback", status_code=202, response_model=SnapshotTaskAccepted)
async def rollback_restoration(restoration_id: str, user: UserPublic = Depends(get_current_user)):
    try:
        return await _commands().rollback(restoration_id, user.id)
    except SnapshotMaintenanceConflict as error:
        raise HTTPException(status_code=423, detail=str(error)) from error
    except SnapshotServerRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TargetIgnoredError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/{snapshot_id}")
async def delete_snapshot(snapshot_id: str, _: UserPublic = Depends(get_current_user)):
    """Delete a specific snapshot by ID"""
    logger = get_logger()
    service = _get_snapshot_service()
    await service.forget_id(snapshot_id=snapshot_id, prune=True)
    logger.info("Snapshot deleted: %s", snapshot_id)
    return {"message": f"Snapshot {snapshot_id} deleted successfully"}


# Backup repository disk usage models


@router.get("/repository-usage", response_model=BackupRepositoryUsage)
async def get_backup_repository_usage(_: UserPublic = Depends(get_current_user)):
    """Get backup repository disk usage information"""
    settings = get_settings()
    if not settings.restic or not settings.restic.repository_path:
        raise HTTPException(
            status_code=500,
            detail="Restic is not configured. Please add restic settings to config.toml",
        )

    repository_path = Path(settings.restic.repository_path)
    disk_info = await get_disk_info(repository_path)

    return BackupRepositoryUsage(
        backupUsedGB=disk_info.used / 1024**3,
        backupTotalGB=disk_info.total / 1024**3,
        backupAvailableGB=(disk_info.total - disk_info.used) / 1024**3,
    )


# Lock management models


@router.get("/locks", response_model=ListLocksResponse)
async def list_locks(_: UserPublic = Depends(get_current_user)):
    """List all locks in the repository"""
    service = _get_snapshot_service()
    locks_output = await service.list_locks()
    return ListLocksResponse(locks=locks_output)


@router.post("/unlock", response_model=UnlockResponse)
async def unlock_repository(_: UserPublic = Depends(get_current_user)):
    """Remove stale locks from the repository"""
    logger = get_logger()
    service = _get_snapshot_service()
    unlock_output = await service.unlock()
    logger.info("Repository unlocked")
    return UnlockResponse(message="Repository unlocked successfully", output=unlock_output)
