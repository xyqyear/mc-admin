"""Global snapshot management endpoints using restic"""

from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path

from aiofiles import os as aioos
from fastapi import APIRouter, Depends, HTTPException

from app.auth.schemas import UserPublic
from app.snapshots.api_models import (
    BackupRepositoryUsage,
    CreateSnapshotRequest,
    CreateSnapshotResponse,
    ListLocksResponse,
    ListSnapshotsResponse,
    RestorePreviewAction,
    RestorePreviewRequest,
    RestorePreviewResponse,
    RestoreRequest,
    UnlockResponse,
)

from ..config import get_settings
from ..cron import get_restart_scheduler
from ..dependencies import get_current_user
from ..dynamic_config import get_config
from ..errors import PublicOperationError, log_safe_error, public_error_message
from ..logger import get_logger
from ..minecraft import get_docker_mc_manager
from ..operation_admission import get_server_write_admission
from ..snapshots import (
    TargetIgnoredError,
    get_snapshot_service,
)
from ..snapshots.application import SnapshotApplication, resolve_backup_paths
from ..snapshots.policy import check_backup_time_restriction
from ..snapshots.restore import (
    SnapshotMaintenanceConflict,
    SnapshotRestoreService,
    SnapshotServerRunning,
)
from ..system.resources import get_disk_info
from ..utils.sse import sse_encode, sse_response
from ..world.locks import get_server_operation_lock

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




# Global snapshot endpoints
@router.post("", response_model=CreateSnapshotResponse)
async def create_global_snapshot(
    request: CreateSnapshotRequest, _: UserPublic = Depends(get_current_user)
):
    """Create a snapshot covering one or more paths (or a server, or all servers)"""
    logger = get_logger()
    await _check_backup_time_restriction()

    backup_paths = await _resolve_backup_paths(request.server_id, request.paths)

    for backup_path in backup_paths:
        if not await aioos.path.exists(backup_path):
            raise HTTPException(status_code=404, detail=f"Path not found: {backup_path}")

    service = _get_snapshot_service()
    try:
        snapshot = await SnapshotApplication(service, get_docker_mc_manager(), get_server_operation_lock()).backup(backup_paths, actor_id=_.id)
    except SnapshotMaintenanceConflict as error:
        raise HTTPException(status_code=423, detail=str(error)) from error
    except TargetIgnoredError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "Snapshot created: %s (server_id=%s)", snapshot.short_id, request.server_id
    )
    return CreateSnapshotResponse(
        message=f"Snapshot created successfully for {len(backup_paths)} path(s)",
        snapshot=snapshot,
    )


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


async def admit_snapshot_restore(
    request: RestoreRequest, _: UserPublic = Depends(get_current_user)
) -> AsyncGenerator[None]:
    admission = (
        get_server_write_admission().write([request.server_id])
        if request.server_id else get_server_write_admission().write_global()
    )
    with admission:
        yield


@router.post("/restore", dependencies=[Depends(admit_snapshot_restore)])
async def restore_global_snapshot(
    request: RestoreRequest, user: UserPublic = Depends(get_current_user)
):
    target_paths = await _resolve_backup_paths(request.server_id, request.paths)
    service = SnapshotRestoreService(
        _get_snapshot_service(), get_docker_mc_manager(), get_server_operation_lock()
    )
    server_ids = await service.maintenance_servers(target_paths)
    try:
        await service.check_available(server_ids)
    except SnapshotMaintenanceConflict as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except SnapshotServerRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    async def event_gen() -> AsyncGenerator[bytes]:
        try:
            completed = None
            async with aclosing(service.restore(
                request.snapshot_id, target_paths, server_ids, user.id
            )) as events:
                async for event in events:
                    if event.get("event_type") == "complete":
                        completed = event
                    else:
                        yield sse_encode(event)
            if completed is not None:
                yield sse_encode(completed)
        except Exception as exc:  # noqa: BLE001 - stream failures need a safe terminal event
            log_safe_error(exc, "Snapshot restore failed")
            if isinstance(exc, (SnapshotMaintenanceConflict, SnapshotServerRunning, TargetIgnoredError)):
                exc = PublicOperationError(str(exc))
            yield sse_encode({"event_type": "error", "message": public_error_message(exc)})

    return sse_response(event_gen())


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
