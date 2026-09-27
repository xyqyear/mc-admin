import asyncio
from pathlib import Path

import aiofiles.os as aioos
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.auth.schemas import UserPublic

from ...background_tasks.api_models import TaskAccepted
from ...dependencies import get_current_user
from ...dynamic_config import get_config
from ...errors import log_safe_error
from ...mcmap import (
    MapStatus,
    ServerMapCache,
    discover_mods_dir,
    get_mcmap_manager,
    palette_is_current,
)
from ...mcmap.initialization import submit_initialization
from ...mcmap.ownership import require_usable_cache
from ...minecraft import get_docker_mc_manager
from ...utils import async_fs
from ...world.region_manifest import list_region_manifest
from .admission import admit_server_io

router = APIRouter(prefix="/servers", tags=["map"])


async def _get_data_path(server_id: str) -> Path:
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    return instance.get_data_path()


async def _resolve_region_path(data_path: Path, region_path: str) -> Path:
    if not region_path or region_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid region path")
    resolved = await async_fs.resolve(data_path / region_path)
    base = await async_fs.resolve(data_path)
    try:
        resolved.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid region path")
    if resolved == base:
        raise HTTPException(status_code=400, detail="Invalid region path")
    if not await aioos.path.isdir(resolved):
        raise HTTPException(status_code=404, detail="Region directory not found")
    return resolved


async def _list_regions(region_dir: Path) -> list[tuple[int, int, int]]:
    return await list_region_manifest(region_dir)


@router.get("/{server_id}/map/status", response_model=MapStatus)
async def get_status(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> MapStatus:
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)

    version: str | None = None
    try:
        compose = await instance.get_compose_obj()
        version = compose.get_game_version()
    except Exception as error:  # noqa: BLE001 - malformed configuration must not expose its values
        log_safe_error(error, "读取地图状态时无法解析服务器配置")
        version = None

    palette_current = False
    if version is not None:
        mods_dir = await discover_mods_dir(data_path)
        try:
            palette_current = await palette_is_current(cache, version, mods_dir)
        except OSError:
            palette_current = False

    return MapStatus(
        client_jar_present=await aioos.path.exists(cache.client_jar),
        palette_present=await aioos.path.exists(cache.palette_json),
        palette_current=palette_current,
        version=version,
    )


@router.get("/{server_id}/map/regions", response_model=list[tuple[int, int, int]])
async def get_regions(
    server_id: str,
    region: str = Query(..., description="Region folder relative to data/"),
    _: UserPublic = Depends(get_current_user),
) -> list[tuple[int, int, int]]:
    data_path = await _get_data_path(server_id)
    region_dir = await _resolve_region_path(data_path, region)
    return await _list_regions(region_dir)


@router.post("/{server_id}/map/initialize", response_model=TaskAccepted, status_code=202,
             dependencies=[Depends(admit_server_io)])
async def initialize(
    server_id: str,
    force: bool = Query(False, description="Delete cached prerequisites first"),
    user: UserPublic = Depends(get_current_user),
) -> TaskAccepted:
    return await submit_initialization(server_id, force, user.id)


@router.get("/{server_id}/map/tiles/{x}/{z}.png", dependencies=[Depends(admit_server_io)])
async def get_tile(
    server_id: str,
    x: int,
    z: int,
    region: str = Query(..., description="Region folder relative to data/"),
    _: UserPublic = Depends(get_current_user),
) -> FileResponse:
    await require_usable_cache(server_id)
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)

    if not await aioos.path.exists(cache.palette_json):
        raise HTTPException(
            status_code=409, detail="Map not initialized — call /initialize first"
        )

    await _resolve_region_path(data_path, region)
    cfg = get_config().mcmap

    state = await cache.is_fresh(region, x, z)
    if state == "missing_mca":
        raise HTTPException(status_code=404, detail="Region not present")
    if state == "fresh":
        return await _png_response(cache.png_path(region, x, z))

    queue = get_mcmap_manager().get_queue(server_id, region, cache)
    try:
        png = await asyncio.wait_for(
            queue.request(x, z), timeout=cfg.request_timeout_seconds
        )
    except TimeoutError:
        raise HTTPException(status_code=503, detail="Render timed out, retry")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Region not present")
    return await _png_response(png)


async def _png_response(png: Path) -> FileResponse:
    # Tile URL carries mtime as `?mt=`; see docs/server-map.md for cache rationale.
    st = await aioos.stat(png)
    return FileResponse(
        str(png),
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=31536000",
            "ETag": f'"{int(st.st_mtime)}"',
        },
    )
