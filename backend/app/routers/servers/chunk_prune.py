from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...background_tasks import TaskType, task_manager
from ...background_tasks.models import BackgroundTask
from ...chunk_prune import (
    ChunkPruneConflictError,
    ChunkPrunePreviewGeometryResponse,
    ChunkPrunePreviewRequest,
    ChunkPruneSettingsResponse,
    ChunkPruneStartResponse,
    ChunkPruneTaskNotFound,
    ChunkPruneValidationError,
    chunk_prune_service,
)
from ...dependencies import get_current_user
from ...dynamic_config import config
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ..tasks import BackgroundTaskResponse

router = APIRouter(prefix="/servers", tags=["chunk-prune"])


class ChunkPruneApplyRequest(BaseModel):
    preview_task_id: str


class ChunkPruneStateResponse(BaseModel):
    preview_task: BackgroundTaskResponse | None
    apply_task: BackgroundTaskResponse | None


def _latest_task(tasks: list[BackgroundTask], task_type: TaskType) -> BackgroundTask | None:
    matching = [task for task in tasks if task.task_type == task_type]
    if not matching:
        return None
    return max(matching, key=lambda task: task.created_at)


@router.get(
    "/{server_id}/chunk-prune/settings",
    response_model=ChunkPruneSettingsResponse,
)
async def get_chunk_prune_settings(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> ChunkPruneSettingsResponse:
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    cfg = config.mcmap
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
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    server_tasks = [
        task for task in task_manager.get_all_tasks() if task.server_id == server_id
    ]
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
        return chunk_prune_service.get_preview_geometry(
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
        task_id = await chunk_prune_service.start_preview(
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
    _: UserPublic = Depends(get_current_user),
) -> ChunkPruneStartResponse:
    try:
        task_id = await chunk_prune_service.start_apply(
            server_id=server_id,
            preview_task_id=body.preview_task_id,
        )
    except ChunkPruneTaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ChunkPruneValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ChunkPruneConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return ChunkPruneStartResponse(task_id=task_id)
