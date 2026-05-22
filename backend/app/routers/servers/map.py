import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator, List, Optional, Tuple

import aiofiles.os as aioos
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from ...dependencies import get_current_user
from ...dynamic_config import config
from ...logger import logger
from ...mcmap import (
    DimensionInfo,
    MapStatus,
    ServerMapCache,
    discover_level_dat,
    discover_mods_dir,
    mcmap_manager,
    palette_is_current,
    write_palette_hash,
)
from ...mcmap import runner as mcmap_runner
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...utils import async_fs
from ...world.dimension_labels import label_for_dimension_dir
from ...world.layout import WorldLayoutDiscoveryError, discover_world_roots
from ...world.region_files import parse_region_filename
from ...world.region_manifest import list_region_manifest

router = APIRouter(prefix="/servers", tags=["map"])


async def _get_data_path(server_id: str) -> Path:
    instance = docker_mc_manager.get_instance(server_id)
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


def _count_region_mca_files_sync(region_dir: Path) -> int:
    count = 0
    try:
        entries = os.scandir(region_dir)
    except OSError:
        return 0
    with entries:
        for entry in entries:
            if parse_region_filename(entry.name) is None:
                continue
            try:
                if entry.is_file(follow_symlinks=False):
                    count += 1
            except OSError:
                continue
    return count


async def _discover_dimensions(data_path: Path) -> List[DimensionInfo]:
    results: List[DimensionInfo] = []
    try:
        roots = await discover_world_roots(data_path)
    except WorldLayoutDiscoveryError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    for root in roots:
        for dim in root.dimensions:
            try:
                region_path = dim.region_dir.relative_to(data_path).as_posix()
            except ValueError:
                continue
            mca_count = await asyncio.to_thread(
                _count_region_mca_files_sync, dim.region_dir
            )
            results.append(
                DimensionInfo(
                    region_path=region_path,
                    label=label_for_dimension_dir(root.path, dim.region_dir.parent),
                    mca_count=mca_count,
                )
            )
    results.sort(key=lambda d: d.region_path)
    return results


async def _list_regions(region_dir: Path) -> List[Tuple[int, int, int]]:
    return await list_region_manifest(region_dir)


@router.get("/{server_id}/map/status", response_model=MapStatus)
async def get_status(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> MapStatus:
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)

    version: Optional[str] = None
    try:
        compose = await instance.get_compose_obj()
        version = compose.get_game_version()
    except Exception:
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


@router.get("/{server_id}/map/dimensions", response_model=List[DimensionInfo])
async def get_dimensions(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> List[DimensionInfo]:
    data_path = await _get_data_path(server_id)
    return await _discover_dimensions(data_path)


@router.get("/{server_id}/map/regions", response_model=List[Tuple[int, int, int]])
async def get_regions(
    server_id: str,
    region: str = Query(..., description="Region folder relative to data/"),
    _: UserPublic = Depends(get_current_user),
) -> List[Tuple[int, int, int]]:
    data_path = await _get_data_path(server_id)
    region_dir = await _resolve_region_path(data_path, region)
    return await _list_regions(region_dir)


def _sse(event_obj: dict) -> bytes:
    return f"data: {json.dumps(event_obj, separators=(',', ':'))}\n\n".encode()


async def _initialize_stream(
    server_id: str,
) -> AsyncGenerator[bytes, None]:
    instance = docker_mc_manager.get_instance(server_id)
    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)
    await cache.ensure_dir(cache.cache_dir)

    try:
        compose = await instance.get_compose_obj()
        version = compose.get_game_version()
    except Exception as e:
        yield _sse(
            {
                "stage": "client",
                "phase": "error",
                "message": f"failed to read compose: {e}",
            }
        )
        return

    # Stage 1: client jar
    if await aioos.path.exists(cache.client_jar):
        yield _sse(
            {"stage": "client", "phase": "done", "percent": 100, "cached": True}
        )
    else:
        yield _sse({"stage": "client", "phase": "starting", "percent": 0})
        try:
            async with mcmap_runner.download_client(
                version, cache.client_jar, owned_by=data_path
            ) as proc:
                async for event in proc:
                    if event.get("type") == "progress":
                        phase = event.get("phase")
                        if phase == "downloading":
                            total = event.get("total") or 0
                            got = event.get("bytes") or 0
                            pct = (got / total * 100) if total else 0
                            yield _sse(
                                {
                                    "stage": "client",
                                    "phase": "downloading",
                                    "percent": pct,
                                    "message": f"Downloading {version} ({got} / {total} bytes)",
                                }
                            )
                        elif phase == "verified":
                            yield _sse(
                                {
                                    "stage": "client",
                                    "phase": "verifying",
                                    "percent": 100,
                                }
                            )
                    elif event.get("type") == "result":
                        yield _sse(
                            {
                                "stage": "client",
                                "phase": "done",
                                "percent": 100,
                                "cached": False,
                            }
                        )
                    elif event.get("type") == "error":
                        yield _sse(
                            {
                                "stage": "client",
                                "phase": "error",
                                "message": event.get("message", "unknown error"),
                            }
                        )
                        return
            if proc.returncode not in (0, None):
                stderr_text = await proc.stderr()
                yield _sse(
                    {
                        "stage": "client",
                        "phase": "error",
                        "message": stderr_text.strip() or "download-client failed",
                    }
                )
                return
        except Exception as e:
            logger.exception("mcmap download-client failed")
            yield _sse({"stage": "client", "phase": "error", "message": str(e)})
            return

    # Stage 2: palette
    mods_dir = await discover_mods_dir(data_path)
    if await palette_is_current(cache, version, mods_dir):
        yield _sse(
            {"stage": "palette", "phase": "done", "percent": 100, "cached": True}
        )
        yield _sse({"stage": "complete"})
        return

    yield _sse({"stage": "palette", "phase": "starting", "percent": 0})
    packs: List[Path] = []
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
            async for event in proc:
                if event.get("type") == "progress":
                    phase = event.get("phase")
                    if phase == "pack_loaded":
                        idx = event.get("index") or 0
                        total = event.get("total") or 1
                        pct = (idx / total * 100) if total else 0
                        path_str = event.get("path", "")
                        yield _sse(
                            {
                                "stage": "palette",
                                "phase": "pack_loaded",
                                "percent": pct,
                                "message": f"Loaded {Path(path_str).name} ({idx} of {total})",
                            }
                        )
                    elif phase == "packs_done":
                        yield _sse(
                            {
                                "stage": "palette",
                                "phase": "resolving",
                                "percent": 100,
                            }
                        )
                elif event.get("type") == "result":
                    await write_palette_hash(cache, version, mods_dir)
                    yield _sse(
                        {
                            "stage": "palette",
                            "phase": "done",
                            "percent": 100,
                            "cached": False,
                        }
                    )
                elif event.get("type") == "error":
                    yield _sse(
                        {
                            "stage": "palette",
                            "phase": "error",
                            "message": event.get("message", "unknown error"),
                        }
                    )
                    return
        if proc.returncode not in (0, None):
            stderr_text = await proc.stderr()
            yield _sse(
                {
                    "stage": "palette",
                    "phase": "error",
                    "message": stderr_text.strip() or "gen-palette failed",
                }
            )
            return
    except Exception as e:
        logger.exception("mcmap gen-palette failed")
        yield _sse({"stage": "palette", "phase": "error", "message": str(e)})
        return

    yield _sse({"stage": "complete"})


@router.post("/{server_id}/map/initialize")
async def initialize(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> StreamingResponse:
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    return StreamingResponse(
        _initialize_stream(server_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{server_id}/map/tiles/{x}/{z}.png")
async def get_tile(
    server_id: str,
    x: int,
    z: int,
    region: str = Query(..., description="Region folder relative to data/"),
    _: UserPublic = Depends(get_current_user),
) -> FileResponse:
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)

    if not await aioos.path.exists(cache.palette_json):
        raise HTTPException(
            status_code=409, detail="Map not initialized — call /initialize first"
        )

    await _resolve_region_path(data_path, region)
    cfg = config.mcmap

    state = await cache.is_fresh(region, x, z)
    if state == "missing_mca":
        raise HTTPException(status_code=404, detail="Region not present")
    if state == "fresh":
        return await _png_response(cache.png_path(region, x, z))

    queue = mcmap_manager.get_queue(server_id, region, cache)
    try:
        png = await asyncio.wait_for(
            queue.request(x, z), timeout=cfg.request_timeout_seconds
        )
    except asyncio.TimeoutError:
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
            "Vary": "Authorization",
            "ETag": f'"{int(st.st_mtime)}"',
        },
    )


@router.delete("/{server_id}/map/cache")
async def clear_dimension_cache(
    server_id: str,
    region: str = Query(..., description="Region folder relative to data/"),
    _: UserPublic = Depends(get_current_user),
) -> dict:
    data_path = await _get_data_path(server_id)
    await _resolve_region_path(data_path, region)
    cache = ServerMapCache(data_path=data_path)
    tiles = cache.tiles_dir(region)
    if await aioos.path.exists(tiles):
        await async_fs.rmtree(tiles)
    return {"cleared": region}
