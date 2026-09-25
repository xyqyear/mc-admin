from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.schemas import UserPublic
from app.chunk_prune.api_models import ChunkPruneApplyRequest, ChunkPruneStateResponse

from ...background_tasks import TaskType
from ...background_tasks.models import BackgroundTask
from ...chunk_prune import (
    ChunkPruneConflictError,
    ChunkPrunePreviewGeometryResponse,
    ChunkPrunePreviewRequest,
    ChunkPruneSettingsResponse,
    ChunkPruneStartResponse,
    ChunkPruneTaskNotFound,
    ChunkPruneValidationError,
    get_chunk_prune_service,
)
from ...dependencies import get_current_user
from ...dynamic_config import get_config
from ...minecraft import get_docker_mc_manager
from ..tasks import BackgroundTaskResponse
from .admission import admit_server_write

router = APIRouter(prefix="/servers", tags=["chunk-prune"])


def _latest_task(tasks: list[BackgroundTask], task_type: TaskType) -> BackgroundTask | None:
    matching = [task for task in tasks if task.task_type == task_type]
    if not matching:
        return None
    return max(matching, key=lambda task: task.created_at)


@router.get(
    "/{server_id}/chunk-prune/settings",
    response_model=ChunkPruneSettingsResponse,
    dependencies=[Depends(admit_server_write)],
)
async def get_chunk_prune_settings(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> ChunkPruneSettingsResponse:
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    cfg = get_config().mcmap
    return ChunkPruneSettingsResponse(
        default_threshold_seconds=cfg.prune_default_threshold_seconds,
    )


@router.get(
    "/{server_id}/chunk-prune/state",
    response_model=ChunkPruneStateResponse,
)
async def get_chunk_prune_state(
    server_id: str,
    _: UserPublic = Depends(get_current_user),
) -> ChunkPruneStateResponse:
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    server_tasks = get_chunk_prune_service().registry.tasks(server_id)
    preview_task = _latest_task(server_tasks, TaskType.CHUNK_PRUNE_PREVIEW)
    apply_task = None
    if preview_task is not None:
        apply_candidates = [
            task
            for task in server_tasks
            if task.task_type == TaskType.CHUNK_PRUNE_APPLY
            and task.created_at >= preview_task.created_at
        ]
        if apply_candidates:
            apply_task = max(apply_candidates, key=lambda task: task.created_at)

    return ChunkPruneStateResponse(
        preview=(get_chunk_prune_service().registry.state(metadata)
                 if preview_task is not None and (metadata := get_chunk_prune_service().registry.metadata.get(preview_task.task_id)) is not None
                 else None),
        preview_task=(
            BackgroundTaskResponse.from_task(preview_task)
            if preview_task is not None
            else None
        ),
        apply_task=(
            BackgroundTaskResponse.from_task(apply_task)
            if apply_task is not None
            else None
        ),
    )


@router.get(
    "/{server_id}/chunk-prune/previews/{preview_task_id}/geometry",
    response_model=ChunkPrunePreviewGeometryResponse,
)
async def get_chunk_prune_preview_geometry(
    server_id: str,
    preview_task_id: str,
    _: UserPublic = Depends(get_current_user),
) -> ChunkPrunePreviewGeometryResponse:
    try:
        return get_chunk_prune_service().get_preview_geometry(
            server_id=server_id,
            preview_task_id=preview_task_id,
        )
    except ChunkPruneTaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ChunkPruneValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{server_id}/chunk-prune/preview",
    response_model=ChunkPruneStartResponse,
)
async def start_chunk_prune_preview(
    server_id: str,
    body: ChunkPrunePreviewRequest,
    user: UserPublic = Depends(get_current_user),
) -> ChunkPruneStartResponse:
    try:
        task_id = await get_chunk_prune_service().start_preview(
            server_id=server_id,
            request=body,
            user_id=user.id,
        )
    except ChunkPruneTaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ChunkPruneValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ChunkPruneStartResponse(task_id=task_id)


@router.post(
    "/{server_id}/chunk-prune/apply",
    response_model=ChunkPruneStartResponse,
)
async def start_chunk_prune_apply(
    server_id: str,
    body: ChunkPruneApplyRequest,
    user: UserPublic = Depends(get_current_user),
) -> ChunkPruneStartResponse:
    try:
        task_id = await get_chunk_prune_service().start_apply(
            server_id=server_id,
            preview_task_id=body.preview_task_id,
            user_id=user.id,
        )
    except ChunkPruneTaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ChunkPruneValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ChunkPruneConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return ChunkPruneStartResponse(task_id=task_id)
