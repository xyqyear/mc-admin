from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.auth.schemas import UserPublic
from app.world.api_models import (
    DimensionInfoResponse,
    DimensionLabelsResponse,
    WorldLayoutResponse,
    WorldRootResponse,
)

from ...dependencies import get_current_user
from ...dynamic_config import get_config
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
from ...world import (
    WorldLayoutDiscoveryError,
    WorldRoot,
    discover_world_root_paths,
    discover_world_roots,
)
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["world-restore"],
    dependencies=[Depends(admit_server_write)],
)


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
