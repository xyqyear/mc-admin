from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...chunk_prune import (
    ChunkPruneConflictError,
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

router = APIRouter(prefix="/servers", tags=["chunk-prune"])


class ChunkPruneApplyRequest(BaseModel):
    preview_task_id: str


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
