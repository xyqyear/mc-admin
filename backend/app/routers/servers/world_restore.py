from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.auth.schemas import UserPublic
from app.world.api_models import (
    DimensionInfoResponse,
    DimensionLabelsResponse,
    PreviewRequest,
    WorldLayoutResponse,
    WorldRootResponse,
)

from ...dependencies import get_current_user
from ...dynamic_config import get_config
from ...errors import log_safe_error, public_error_message
from ...ftb_claims import (
    ClaimsResponse,
    FtbExtractError,
    extract_claims_for_server,
)
from ...minecraft import get_docker_mc_manager
from ...player_locations import (
    PlayerLocationExtractError,
    PlayerLocationsResponse,
    extract_player_locations_for_server,
)
from ...utils.sse import sse_encode, sse_response
from ...world import (
    SelectionResolutionError,
    WorldLayoutDiscoveryError,
    WorldRoot,
    discover_world_root_paths,
    discover_world_roots,
)
from ...world.preview import PreviewDiskGuardError, PreviewSessionNotFoundError
from ...world.preview_service import get_world_preview_service
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["world-restore"],
    dependencies=[Depends(admit_server_write)],
)


def _get_previews():
    previews = get_world_preview_service()
    if not previews:
        raise HTTPException(
            status_code=503,
            detail="尚未配置快照仓库，无法预览恢复结果",
        )
    return previews


async def _ensure_server_exists(server_id: str) -> None:
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")


def _world_root_to_response(root: WorldRoot) -> WorldRootResponse:
    return WorldRootResponse(
        name=root.name,
        path=str(root.path),
        dimensions=[
            DimensionInfoResponse(
                region_dir=str(d.region_dir),
                entities_dir=str(d.entities_dir) if d.entities_dir else None,
                poi_dir=str(d.poi_dir) if d.poi_dir else None,
            )
            for d in root.dimensions
        ],
    )


async def _get_world_roots(data_path: Path) -> list[WorldRoot]:
    try:
        return await discover_world_roots(data_path)
    except WorldLayoutDiscoveryError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{server_id}/world-restore/layout", response_model=WorldLayoutResponse)
async def get_layout(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> WorldLayoutResponse:
    await _ensure_server_exists(server_id)
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()

    roots = await _get_world_roots(data_path)
    return WorldLayoutResponse(world_roots=[_world_root_to_response(r) for r in roots])


@router.get(
    "/{server_id}/world-restore/dimension-labels",
    response_model=DimensionLabelsResponse,
)
async def get_dimension_labels(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> DimensionLabelsResponse:
    await _ensure_server_exists(server_id)
    return DimensionLabelsResponse(
        dimension_labels=dict(get_config().world.dimension_labels)
    )


@router.get(
    "/{server_id}/claims",
    response_model=ClaimsResponse,
)
@router.get(
    "/{server_id}/world-restore/claims",
    response_model=ClaimsResponse,
)
async def get_ftb_claims(
    server_id: str,
    _: UserPublic = Depends(get_current_user),
) -> ClaimsResponse:
    await _ensure_server_exists(server_id)
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()
    roots = await discover_world_root_paths(data_path)
    if not roots:
        return ClaimsResponse(available=False)
    try:
        return await extract_claims_for_server(
            data_path,
            world_root=roots[0],
        )
    except FtbExtractError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{server_id}/player-locations",
    response_model=PlayerLocationsResponse,
)
@router.get(
    "/{server_id}/world-restore/player-locations",
    response_model=PlayerLocationsResponse,
)
async def get_player_locations(
    server_id: str,
    _: UserPublic = Depends(get_current_user),
) -> PlayerLocationsResponse:
    await _ensure_server_exists(server_id)
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()
    roots = await discover_world_root_paths(data_path)
    if not roots:
        return PlayerLocationsResponse()
    try:
        return await extract_player_locations_for_server(
            data_path,
            world_root=roots[0],
        )
    except PlayerLocationExtractError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{server_id}/world-restore/preview")
async def begin_preview(
    server_id: str,
    body: PreviewRequest,
    _: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    await _ensure_server_exists(server_id)
    orch = _get_previews()

    async def event_gen() -> AsyncGenerator[bytes]:
        try:
            async with aclosing(
                orch.begin_preview(
                    server_id=server_id,
                    source_snapshot_id=body.source_snapshot_id,
                    selection=body.selection,
                )
            ) as events:
                async for event in events:
                    yield sse_encode(event.model_dump(exclude_none=True))
        except PreviewDiskGuardError as e:
            yield sse_encode(
                {
                    "event_type": "error",
                    "message": str(e),
                    "free": e.free,
                    "required": e.required,
                }
            )
        except SelectionResolutionError as e:
            yield sse_encode({"event_type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001 - preview failures must exclude raw adapter diagnostics
            log_safe_error(e, "World preview stream failed")
            yield sse_encode(
                {"event_type": "error", "message": public_error_message(e)}
            )

    return sse_response(event_gen())


@router.post(
    "/{server_id}/world-restore/preview/{session_id}/heartbeat",
    status_code=204,
)
async def heartbeat_preview(
    server_id: str,
    session_id: str,
    _: UserPublic = Depends(get_current_user),
) -> None:
    await _ensure_server_exists(server_id)
    orch = _get_previews()
    try:
        await orch.require_preview_owner(server_id, session_id)
        orch.heartbeat_preview(session_id)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")


@router.delete(
    "/{server_id}/world-restore/preview/{session_id}",
    status_code=204,
)
async def end_preview(
    server_id: str,
    session_id: str,
    _: UserPublic = Depends(get_current_user),
) -> None:
    await _ensure_server_exists(server_id)
    orch = _get_previews()
    try:
        await orch.require_preview_owner(server_id, session_id, missing_ok=True)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")
    await orch.end_preview(session_id)


@router.get("/{server_id}/world-restore/preview/{session_id}/tile/{rx}/{rz}.png")
async def get_preview_tile(
    server_id: str,
    session_id: str,
    rx: int,
    rz: int,
    _: UserPublic = Depends(get_current_user),
) -> Response:
    await _ensure_server_exists(server_id)
    orch = _get_previews()

    # Heartbeat before awaiting render so coalesced bursts keep the session alive.
    try:
        await orch.require_preview_owner(server_id, session_id)
        orch.heartbeat_preview(session_id)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")

    try:
        tile = await orch.read_preview_tile(session_id, rx, rz)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Preview tile not available")
    except TimeoutError:
        raise HTTPException(status_code=503, detail="Render timed out, retry")
    return Response(
        tile,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=60",
        },
    )
