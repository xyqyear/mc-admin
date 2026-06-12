"""Global snapshot management endpoints using restic"""

from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, List, Optional

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
from ..system.resources import get_disk_info
from ..utils import async_fs
from ..utils.sse import sse_encode, sse_response
from ..world import png_invalidate

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


def _get_snapshot_service():
    if not snapshot_service:
        raise HTTPException(
            status_code=500,
            detail="Restic is not configured. Please add restic settings to config.toml",
        )
    return snapshot_service


async def _resolve_backup_paths(
    server_id: Optional[str], paths: Optional[List[str]]
) -> List[Path]:
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
    server_id: Optional[str] = None
    paths: Optional[List[str]] = None


class RestorePreviewRequest(BaseModel):
    snapshot_id: str
    server_id: Optional[str] = None
    paths: Optional[List[str]] = None


class RestoreRequest(BaseModel):
    snapshot_id: str
    server_id: Optional[str] = None
    paths: Optional[List[str]] = None


class CreateSnapshotResponse(BaseModel):
    message: str
    snapshot: ResticSnapshotWithSummary


class ListSnapshotsResponse(BaseModel):
    snapshots: List[ResticSnapshot]


class RestorePreviewAction(BaseModel):
    action: ResticRestoreAction
    item: Optional[str] = None
    size: Optional[int] = None


class RestorePreviewResponse(BaseModel):
    actions: List[RestorePreviewAction]
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
    server_id: Optional[str] = None,
    path: Optional[str] = None,
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


async def _invalidate_pngs_across_instances(items: list[str]) -> int:
    """Walk every known docker MC instance and delete cached tiles for any
    region MCAs the restore touched that fall under that instance's data dir.

    Items outside any registered instance are ignored — the most common reason
    is a restore covering paths that aren't Minecraft worlds at all.
    """
    if not items:
        return 0
    instances = await docker_mc_manager.get_all_instances()
    total = 0
    for instance in instances:
        data_path = instance.get_data_path()
        if not await aioos.path.exists(data_path):
            continue
        pngs = png_invalidate.pngs_for_restic_items(data_path, items)
        if pngs:
            total += await png_invalidate.delete_pngs(pngs)
    return total


@router.post("/restore")
async def restore_global_snapshot(
    request: RestoreRequest, _: UserPublic = Depends(get_current_user)
):
    """Restore a snapshot, streaming progress as Server-Sent Events.

    The flow is: safety snapshot → in-place restic restore (with byte
    progress) → tile-cache invalidation → complete. Any failure terminates
    the stream with an ``error`` event.
    """
    target_paths = await _resolve_backup_paths(request.server_id, request.paths)
    service = _get_snapshot_service()

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            yield sse_encode(
                {
                    "event_type": "start",
                    "message": f"restoring snapshot {request.snapshot_id[:8]}",
                }
            )

            yield sse_encode(
                {
                    "event_type": "safety_snapshot",
                    "message": "creating safety snapshot",
                }
            )
            try:
                safety_snapshot = await service.create_snapshot(target_paths)
            except Exception as e:
                logger.error(
                    "Safety snapshot failed (snapshot_id=%s, server_id=%s, paths=%s): %s",
                    request.snapshot_id,
                    request.server_id,
                    request.paths,
                    e,
                    exc_info=True,
                )
                yield sse_encode(
                    {
                        "event_type": "error",
                        "message": f"failed to create safety snapshot: {e}",
                    }
                )
                return
            yield sse_encode(
                {
                    "event_type": "safety_snapshot",
                    "safety_snapshot_id": safety_snapshot.id,
                    "message": f"safety snapshot {safety_snapshot.short_id}",
                }
            )

            yield sse_encode(
                {
                    "event_type": "restore",
                    "message": f"restoring {len(target_paths)} path(s)",
                    "percent": 0.0,
                }
            )
            touched_items: list[str] = []
            try:
                async for ev in service.restore(
                    request.snapshot_id, target_paths
                ):
                    if ev.kind == "status" and ev.percent_done is not None:
                        yield sse_encode(
                            {
                                "event_type": "restore",
                                "percent": ev.percent_done * 100.0,
                            }
                        )
                    elif ev.kind == "file" and ev.action in (
                        "updated",
                        "restored",
                        "deleted",
                    ):
                        if ev.item is not None:
                            touched_items.append(ev.item)
            except Exception as e:
                logger.error(
                    "Restore failed (snapshot_id=%s, server_id=%s, paths=%s): %s",
                    request.snapshot_id,
                    request.server_id,
                    request.paths,
                    e,
                    exc_info=True,
                )
                yield sse_encode({"event_type": "error", "message": str(e)})
                return

            invalidated = await _invalidate_pngs_across_instances(touched_items)
            yield sse_encode(
                {
                    "event_type": "invalidate_cache",
                    "message": f"invalidated {invalidated} map tile(s)",
                }
            )

            paths_repr = ", ".join(str(p) for p in target_paths)
            logger.info(
                "Restore completed: snapshot=%s safety_snapshot=%s server_id=%s paths=%s tiles=%d",
                request.snapshot_id,
                safety_snapshot.short_id,
                request.server_id,
                paths_repr,
                invalidated,
            )
            yield sse_encode(
                {
                    "event_type": "complete",
                    "message": f"restored snapshot {request.snapshot_id[:8]}",
                    "safety_snapshot_id": safety_snapshot.id,
                }
            )
        except Exception as e:
            logger.exception(
                "Restore stream failed (snapshot_id=%s)", request.snapshot_id
            )
            yield sse_encode({"event_type": "error", "message": str(e)})

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
