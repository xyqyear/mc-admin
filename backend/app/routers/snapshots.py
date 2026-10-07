"""Global snapshot management endpoints using restic"""

import posixpath
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParameter
from fastapi.responses import Response

from app.auth.schemas import UserPublic
from app.snapshots.api_models import (
    ActiveRestorationsResponse,
    BackupRepositoryUsage,
    CheckWorldSnapshotTargetRequest,
    CreateSnapshotRequest,
    ListLocksResponse,
    ListRestorationsResponse,
    ListSnapshotsResponse,
    RestorationResponse,
    RestoreRequest,
    SnapshotTargetCheck,
    SnapshotTargetRules,
    SnapshotTaskAccepted,
    UpdateSnapshotNoteRequest,
)

from ..background_tasks import get_task_manager
from ..config import get_settings
from ..cron import get_restart_scheduler
from ..db.database import get_session_factory
from ..dependencies import get_current_user
from ..dynamic_config import get_config
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
from ..snapshots.maintenance import SnapshotMaintenance
from ..snapshots.models import ResticSnapshot
from ..snapshots.policy import check_backup_time_restriction
from ..snapshots.preview_models import PreviewActions, PreviewRequest, PreviewResult
from ..snapshots.previews import get_snapshot_previews
from ..snapshots.queries import RestorationQueries
from ..snapshots.restoration_models import RestorationStatus
from ..snapshots.rules import read_target_rules
from ..system.resources import get_disk_info

router = APIRouter(
    prefix="/snapshots",
    tags=["snapshots"],
)


async def _check_backup_time_restriction():
    if get_config().snapshots.time_restriction.enabled:
        await check_backup_time_restriction(
            get_config().snapshots.time_restriction,
            await get_restart_scheduler().get_backup_minutes(),
            datetime.now(UTC).astimezone(),
        )


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
    return await resolve_backup_paths(
        get_docker_mc_manager(), Path(settings.server_path), server_id, paths
    )


def _commands():
    commands = get_snapshot_commands()
    if commands is None:
        raise HTTPException(status_code=500, detail="尚未配置快照仓库")
    return commands


@router.post("", status_code=202, response_model=SnapshotTaskAccepted)
async def create_global_snapshot(
    request: CreateSnapshotRequest, user: UserPublic = Depends(get_current_user)
):
    await _check_backup_time_restriction()
    try:
        return await _commands().create(request.scope, user.id, request.note)
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
        resolved = await _resolve_backup_paths(server_id, [path] if path else None)
        filter_path = (
            Path(posixpath.normpath(str(get_docker_mc_manager().get_instance(server_id).get_data_path() / path.lstrip("/"))))
            if path else resolved[0]
        )
    else:
        filter_path = None

    snapshots = await service.list_snapshots(path_filter=filter_path)
    return ListSnapshotsResponse(snapshots=snapshots)


@router.put("/{snapshot_id}/note", response_model=ResticSnapshot)
async def update_snapshot_note(
    request: UpdateSnapshotNoteRequest,
    snapshot_id: str = PathParameter(pattern="^[0-9a-f]{64}$"),
    _: UserPublic = Depends(get_current_user),
):
    return await _get_snapshot_service().save_note(snapshot_id, request.note)


@router.post("/eligible", response_model=ListSnapshotsResponse)
async def eligible_snapshots(
    request: CreateSnapshotRequest, _: UserPublic = Depends(get_current_user)
):
    try:
        return ListSnapshotsResponse(
            snapshots=await _commands().eligible(request.scope)
        )
    except TargetIgnoredError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/targets/rules", response_model=SnapshotTargetRules)
async def get_snapshot_target_rules(
    server_id: str = Query(min_length=1),
    _: UserPublic = Depends(get_current_user),
):
    _commands()
    return await read_target_rules(
        server_id,
        sessions=get_session_factory(),
        root=get_settings().server_path,
        ignored_paths=get_config().snapshots.ignored_paths,
    )


@router.post("/targets/check", response_model=SnapshotTargetCheck)
async def check_world_snapshot_target(
    request: CheckWorldSnapshotTargetRequest, _: UserPublic = Depends(get_current_user)
):
    return await _commands().check_world_target(request.scope)


def _previews():
    previews = get_snapshot_previews()
    if previews is None:
        raise HTTPException(
            status_code=503, detail="尚未配置快照仓库，无法预览恢复结果"
        )
    return previews


@router.post("/previews", status_code=202, response_model=SnapshotTaskAccepted)
async def prepare_preview(
    request: PreviewRequest, user: UserPublic = Depends(get_current_user)
):
    try:
        return await _previews().submit(
            request.scope, request.source_snapshot_id, user.id
        )
    except TargetIgnoredError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/previews/{preview_id}", response_model=PreviewResult)
async def get_preview(preview_id: str, _: UserPublic = Depends(get_current_user)):
    return await _previews().get(preview_id)


@router.get("/previews/{preview_id}/actions", response_model=PreviewActions)
async def get_preview_actions(
    preview_id: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    _: UserPublic = Depends(get_current_user),
):
    return await _previews().actions(preview_id, cursor, limit)


@router.post("/previews/{preview_id}/heartbeat", status_code=204)
async def heartbeat_preview(
    preview_id: str, _: UserPublic = Depends(get_current_user)
) -> None:
    await _previews().heartbeat(preview_id)


@router.delete(
    "/previews/{preview_id}", status_code=202, response_model=SnapshotTaskAccepted
)
async def close_preview(preview_id: str, user: UserPublic = Depends(get_current_user)):
    return await _previews().end(preview_id, user.id)


@router.get("/previews/{preview_id}/tiles/{rx}/{rz}.png")
async def get_preview_tile(
    preview_id: str, rx: int, rz: int, _: UserPublic = Depends(get_current_user)
):
    try:
        tile = await _previews().tile(preview_id, rx, rz)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="该区域没有可预览的地形") from error
    except TimeoutError as error:
        raise HTTPException(
            status_code=503, detail="预览瓦片仍在生成，请稍后重试"
        ) from error
    return Response(
        content=tile, media_type="image/png", headers={"Cache-Control": "private, max-age=60"}
    )


@router.post("/restorations", status_code=202, response_model=SnapshotTaskAccepted)
async def restore_snapshot(
    request: RestoreRequest, user: UserPublic = Depends(get_current_user)
):
    try:
        return await _commands().restore(
            request.scope,
            request.source_snapshot_id,
            user.id,
            entry_point=request.entry_point,
            preview_id=request.preview_id,
        )
    except SnapshotMaintenanceConflict as error:
        raise HTTPException(status_code=423, detail=str(error)) from error
    except SnapshotServerRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TargetIgnoredError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/restorations", response_model=ListRestorationsResponse)
async def list_restorations(
    server_id: str | None = None,
    kind: Literal["global", "server", "paths", "world"] | None = None,
    status: RestorationStatus | None = None,
    entry_point: Literal["files", "world", "snapshots", "history"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: UserPublic = Depends(get_current_user),
):
    return await RestorationQueries(
        get_session_factory(), _get_snapshot_service()
    ).history(server_id, limit, offset, kind=kind, status=status, entry_point=entry_point)


@router.get("/restorations/active", response_model=ActiveRestorationsResponse)
async def active_restorations(
    server_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: UserPublic = Depends(get_current_user),
):
    return await RestorationQueries(get_session_factory()).active(server_id, limit, offset)


@router.get("/restorations/{restoration_id}", response_model=RestorationResponse)
async def get_restoration(
    restoration_id: str, _: UserPublic = Depends(get_current_user)
):
    return await RestorationQueries(get_session_factory(), _get_snapshot_service()).get(
        restoration_id
    )


@router.post(
    "/restorations/{restoration_id}/rollback",
    status_code=202,
    response_model=SnapshotTaskAccepted,
)
async def rollback_restoration(
    restoration_id: str, user: UserPublic = Depends(get_current_user)
):
    try:
        return await _commands().rollback(restoration_id, user.id)
    except SnapshotMaintenanceConflict as error:
        raise HTTPException(status_code=423, detail=str(error)) from error
    except SnapshotServerRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TargetIgnoredError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# Backup repository disk usage models


@router.get("/usage", response_model=BackupRepositoryUsage)
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


@router.post("/unlock", status_code=202, response_model=SnapshotTaskAccepted)
async def unlock_repository(user: UserPublic = Depends(get_current_user)):
    return await SnapshotMaintenance(
        _get_snapshot_service(), get_task_manager()
    ).submit(user.id)


@router.delete("/{snapshot_id}", status_code=202, response_model=SnapshotTaskAccepted)
async def delete_snapshot(
    snapshot_id: str = PathParameter(pattern="^[0-9a-f]{64}$"),
    user: UserPublic = Depends(get_current_user),
):
    return await SnapshotMaintenance(
        _get_snapshot_service(), get_task_manager()
    ).submit(user.id, snapshot_id=snapshot_id)
