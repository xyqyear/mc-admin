"""Global snapshot management endpoints using restic"""

from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path

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
    ResticRestoreAction,
    ResticSnapshot,
    ResticSnapshotWithSummary,
    TargetIgnoredError,
    snapshot_service,
)
from ..snapshots.restore import (
    SnapshotMaintenanceConflict,
    SnapshotRestoreService,
    SnapshotServerRunning,
)
from ..system.resources import get_disk_info
from ..utils import async_fs
from ..utils.sse import sse_encode, sse_response
from ..world.locks import LockHolder, ServerOperationKind, server_operation_lock
from ..world.maintenance import affected_servers

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

    now = datetime.now(UTC).astimezone()
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


def _get_snapshot_service():
    if not snapshot_service:
        raise HTTPException(
            status_code=500,
            detail="Restic is not configured. Please add restic settings to config.toml",
        )
    return snapshot_service


async def _resolve_backup_paths(
    server_id: str | None, paths: list[str] | None
) -> list[Path]:
    """
    Resolve the absolute backup paths from request parameters.

    Every resolved path (symlinks followed) must stay inside the servers
    root — and, for ``paths``, inside the server's data directory — so
    traversal like ``../`` can never reach other servers or the host.

    Args:
        server_id: Optional server identifier
        paths: Optional list of paths within the server's data directory

    Returns:
        List of absolute paths to back up or restore
    """
    if not server_id and not paths:
        # Backup entire servers directory
        return [await async_fs.resolve(settings.server_path)]

    if not server_id:
        error_msg = "Cannot specify paths without server_id"
        logger.error(
            f"Snapshot path resolution failed: {error_msg} (server_id={server_id}, paths={paths})"
        )
        raise HTTPException(status_code=400, detail=error_msg)

    instance = docker_mc_manager.get_instance(server_id)
    try:
        project_path = await async_fs.resolve_inside(
            Path(settings.server_path), instance.get_project_path()
        )
        if not paths:
            return [project_path]

        data_path = instance.get_data_path()
        return [
            await async_fs.resolve_inside(data_path, data_path / p.lstrip("/"))
            for p in paths
        ]
    except async_fs.PathOutsideBaseError as e:
        logger.warning(
            "Snapshot path escape rejected (server_id=%s, paths=%s): %s",
            server_id,
            paths,
            e,
        )
        raise HTTPException(status_code=400, detail="路径越界：目标路径不在服务器目录内")


# Request/Response models
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


# Global snapshot endpoints
@router.post("", response_model=CreateSnapshotResponse)
async def create_global_snapshot(
    request: CreateSnapshotRequest, _: UserPublic = Depends(get_current_user)
):
    """Create a snapshot covering one or more paths (or a server, or all servers)"""
    await _check_backup_time_restriction()

    backup_paths = await _resolve_backup_paths(request.server_id, request.paths)

    for backup_path in backup_paths:
        if not await aioos.path.exists(backup_path):
            raise HTTPException(status_code=404, detail=f"Path not found: {backup_path}")

    service = _get_snapshot_service()
    try:
        server_ids = await affected_servers(docker_mc_manager, backup_paths)
        holder = LockHolder(
            kind=ServerOperationKind.BACKUP, started_at=datetime.now(UTC),
            user_id=_.id, description="手动快照",
        )
        async with server_operation_lock.try_acquire_servers(server_ids, holder) as acquired:
            if not acquired:
                raise HTTPException(status_code=423, detail="服务器正在维护")
            snapshot = await service.create_snapshot(backup_paths)
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


@router.post("/restore")
async def restore_global_snapshot(
    request: RestoreRequest, user: UserPublic = Depends(get_current_user)
):
    target_paths = await _resolve_backup_paths(request.server_id, request.paths)
    service = SnapshotRestoreService(
        _get_snapshot_service(), docker_mc_manager, server_operation_lock
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
            async with aclosing(service.restore(
                request.snapshot_id, target_paths, server_ids, user.id
            )) as events:
                async for event in events:
                    yield sse_encode(event)
        except Exception as exc:
            logger.exception("Snapshot restore failed: snapshot=%s", request.snapshot_id)
            yield sse_encode({"event_type": "error", "message": str(exc)})

    return sse_response(event_gen())


@router.delete("/{snapshot_id}")
async def delete_snapshot(snapshot_id: str, _: UserPublic = Depends(get_current_user)):
    """Delete a specific snapshot by ID"""
    service = _get_snapshot_service()
    await service.forget_id(snapshot_id=snapshot_id, prune=True)
    logger.info("Snapshot deleted: %s", snapshot_id)
    return {"message": f"Snapshot {snapshot_id} deleted successfully"}


# Backup repository disk usage models
class BackupRepositoryUsage(BaseModel):
    backupUsedGB: float
    backupTotalGB: float
    backupAvailableGB: float


@router.get("/repository-usage", response_model=BackupRepositoryUsage)
async def get_backup_repository_usage(_: UserPublic = Depends(get_current_user)):
    """Get backup repository disk usage information"""
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
class ListLocksResponse(BaseModel):
    locks: str


class UnlockResponse(BaseModel):
    message: str
    output: str


@router.get("/locks", response_model=ListLocksResponse)
async def list_locks(_: UserPublic = Depends(get_current_user)):
    """List all locks in the repository"""
    service = _get_snapshot_service()
    locks_output = await service.list_locks()
    return ListLocksResponse(locks=locks_output)


@router.post("/unlock", response_model=UnlockResponse)
async def unlock_repository(_: UserPublic = Depends(get_current_user)):
    """Remove stale locks from the repository"""
    service = _get_snapshot_service()
    unlock_output = await service.unlock()
    logger.info("Repository unlocked")
    return UnlockResponse(message="Repository unlocked successfully", output=unlock_output)
