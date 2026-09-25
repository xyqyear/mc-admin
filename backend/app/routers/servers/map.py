import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path

import aiofiles.os as aioos
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.auth.schemas import UserPublic

from ...dependencies import get_current_user
from ...dynamic_config import get_config
from ...errors import log_safe_error, public_error_message
from ...files.resources import path_claims, require_same_claims
from ...logger import get_logger
from ...mcmap import (
    MapStatus,
    ServerMapCache,
    discover_level_dat,
    discover_mods_dir,
    get_mcmap_manager,
    palette_is_current,
    write_palette_hash,
)
from ...mcmap import runner as mcmap_runner
from ...mcmap.events import (
    MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER,
    MCMAP_GEN_PALETTE_EVENT_ADAPTER,
    MCMapDownloadClientResultEvent,
    MCMapErrorEvent,
    MCMapGenPaletteResultEvent,
    MCMapProgressEvent,
)
from ...mcmap.ownership import require_usable_cache
from ...mcmap.types import MCMapError
from ...minecraft import get_docker_mc_manager
from ...operations.context import current_execution, record_phase
from ...operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from ...operations.execution import operation_scope, settle_before_release
from ...operations.finalization import finalize
from ...operations.journal_types import OperationState
from ...utils import async_fs
from ...utils.sse import sse_encode, sse_response
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


async def _clear_prerequisite_cache(cache: ServerMapCache) -> None:
    for path in (cache.client_jar, cache.palette_json, cache.palette_hash_file):
        try:
            await aioos.unlink(path)
        except FileNotFoundError:
            pass


async def _initialize_stream(
    server_id: str,
    *,
    force: bool = False,
    actor_id: int | None = None,
) -> AsyncGenerator[bytes]:
    instance = get_docker_mc_manager().get_instance(server_id)
    data = instance.get_data_path()

    async def claims_for_cache():
        files = await path_claims(data.parent, [data / ".mcmap"], server_id=server_id)
        return (*files, ResourceClaim(ResourceKind.MAP_CACHE, server_id))

    claims = await claims_for_cache()
    complete: bytes | None = None
    async with (
        operation_scope("map_initialize", [server_id], actor_id=actor_id, claims=claims),
        get_operation_coordinator().acquire(claims),
        settle_before_release(),
    ):
        require_same_claims(claims, await claims_for_cache())
        await require_usable_cache(server_id)
        await record_phase("initializing_map", changed=True)
        async with aclosing(_initialize_owned_stream(server_id, force=force)) as events:
            async for chunk in events:
                event = json.loads(chunk.decode().removeprefix("data: ").strip())
                if event.get("stage") == "complete" or event.get("phase") == "error":
                    complete = chunk
                    if event.get("phase") == "error" and (execution := current_execution()) is not None:
                        execution.outcome = OperationState.FAILED
                else:
                    yield chunk
    if complete is not None:
        yield complete


async def _initialize_owned_stream(
    server_id: str,
    *,
    force: bool = False,
) -> AsyncGenerator[bytes]:
    logger = get_logger()
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)
    await async_fs.resolve_inside(data_path, cache.cache_dir)
    await finalize(cache.ensure_dir(cache.cache_dir))

    if force:
        try:
            await finalize(_clear_prerequisite_cache(cache))
        except OSError as e:
            log_safe_error(e, "清理地图缓存失败")
            yield sse_encode(
                {
                    "stage": "client",
                    "phase": "error",
                    "message": public_error_message(e),
                }
            )
            return

    try:
        compose = await instance.get_compose_obj()
        version = compose.get_game_version()
    except Exception as e:  # noqa: BLE001 - configuration errors remain safe SSE failures
        log_safe_error(e, "初始化地图时无法解析服务器配置")
        yield sse_encode(
            {
                "stage": "client",
                "phase": "error",
                "message": public_error_message(e),
            }
        )
        return

    # Stage 1: client jar
    if await aioos.path.exists(cache.client_jar):
        yield sse_encode(
            {"stage": "client", "phase": "done", "percent": 100, "cached": True}
        )
    else:
        yield sse_encode({"stage": "client", "phase": "starting", "percent": 0})
        try:
            async with mcmap_runner.download_client(
                version, cache.client_jar, owned_by=data_path
            ) as proc:
                async for event in proc.events(MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER):
                    if isinstance(event, MCMapProgressEvent):
                        if event.phase == "downloading":
                            total = event.total or 0
                            got = event.bytes or 0
                            pct = (got / total * 100) if total else 0
                            yield sse_encode(
                                {
                                    "stage": "client",
                                    "phase": "downloading",
                                    "percent": pct,
                                    "message": f"Downloading {version} ({got} / {total} bytes)",
                                }
                            )
                        elif event.phase == "verified":
                            yield sse_encode(
                                {
                                    "stage": "client",
                                    "phase": "verifying",
                                    "percent": 100,
                                }
                            )
                    elif isinstance(event, MCMapDownloadClientResultEvent):
                        yield sse_encode(
                            {
                                "stage": "client",
                                "phase": "done",
                                "percent": 100,
                                "cached": False,
                            }
                        )
                    elif isinstance(event, MCMapErrorEvent):
                        log_safe_error(MCMapError(event.message), "地图客户端下载失败")
                        yield sse_encode(
                            {
                                "stage": "client",
                                "phase": "error",
                                "message": "地图客户端下载失败，请稍后重试",
                            }
                        )
                        return
            if proc.returncode not in (0, None):
                logger.error("地图客户端下载失败: exit_code=%s", proc.returncode)
                yield sse_encode(
                    {
                        "stage": "client",
                        "phase": "error",
                        "message": "地图客户端下载失败，请稍后重试",
                    }
                )
                return
        except Exception as e:  # noqa: BLE001 - adapter exception values are not public output
            log_safe_error(e, "地图客户端下载失败")
            yield sse_encode({"stage": "client", "phase": "error", "message": public_error_message(e)})
            return

    # Stage 2: palette
    mods_dir = await discover_mods_dir(data_path)
    if await palette_is_current(cache, version, mods_dir):
        yield sse_encode(
            {"stage": "palette", "phase": "done", "percent": 100, "cached": True}
        )
        yield sse_encode({"stage": "complete"})
        return

    yield sse_encode({"stage": "palette", "phase": "starting", "percent": 0})
    packs: list[Path] = []
    if mods_dir is not None:
        packs.append(mods_dir)
    packs.append(cache.client_jar)
    level_dat = await discover_level_dat(data_path)

    try:
        async with mcmap_runner.gen_palette(
            packs,
            cache.palette_json,
            level_dat=level_dat,
            owned_by=data_path,
        ) as proc:
            async for event in proc.events(MCMAP_GEN_PALETTE_EVENT_ADAPTER):
                if isinstance(event, MCMapProgressEvent):
                    if event.phase == "pack_loaded":
                        idx = event.index or 0
                        total = event.total or 1
                        pct = (idx / total * 100) if total else 0
                        path_str = event.path or ""
                        yield sse_encode(
                            {
                                "stage": "palette",
                                "phase": "pack_loaded",
                                "percent": pct,
                                "message": f"Loaded {Path(path_str).name} ({idx} of {total})",
                            }
                        )
                    elif event.phase == "packs_done":
                        yield sse_encode(
                            {
                                "stage": "palette",
                                "phase": "resolving",
                                "percent": 100,
                            }
                        )
                elif isinstance(event, MCMapGenPaletteResultEvent):
                    await finalize(write_palette_hash(cache, version, mods_dir))
                    yield sse_encode(
                        {
                            "stage": "palette",
                            "phase": "done",
                            "percent": 100,
                            "cached": False,
                        }
                    )
                elif isinstance(event, MCMapErrorEvent):
                    log_safe_error(MCMapError(event.message), "地图调色板生成失败")
                    yield sse_encode(
                        {
                            "stage": "palette",
                            "phase": "error",
                            "message": "地图调色板生成失败，请稍后重试",
                        }
                    )
                    return
        if proc.returncode not in (0, None):
            logger.error("地图调色板生成失败: exit_code=%s", proc.returncode)
            yield sse_encode(
                {
                    "stage": "palette",
                    "phase": "error",
                    "message": "地图调色板生成失败，请稍后重试",
                }
            )
            return
    except Exception as e:  # noqa: BLE001 - adapter exception values are not public output
        log_safe_error(e, "地图调色板生成失败")
        yield sse_encode({"stage": "palette", "phase": "error", "message": public_error_message(e)})
        return

    yield sse_encode({"stage": "complete"})


@router.post("/{server_id}/map/initialize", dependencies=[Depends(admit_server_io)])
async def initialize(
    server_id: str,
    force: bool = Query(False, description="Delete cached prerequisites first"),
    _: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    return sse_response(_initialize_stream(server_id, force=force, actor_id=_.id))


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
