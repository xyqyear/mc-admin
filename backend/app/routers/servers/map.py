"""Per-server map (mcmap) endpoints."""

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import AsyncGenerator, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from ...dependencies import get_current_user
from ...dynamic_config import config
from ...logger import logger
from ...mcmap import (
    DimensionInfo,
    MapStatus,
    ServerMapCache,
    discover_mods_dir,
    mcmap_manager,
    palette_is_current,
    write_palette_hash,
)
from ...mcmap import runner as mcmap_runner
from ...minecraft import docker_mc_manager
from ...models import UserPublic

router = APIRouter(prefix="/servers", tags=["map"])

REGION_FILE_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


async def _get_data_path(server_id: str) -> Path:
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    return instance.get_data_path()


def _resolve_region_path(data_path: Path, region_path: str) -> Path:
    """Validate that region_path resolves to a directory strictly inside data_path."""
    if not region_path or region_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid region path")
    resolved = (data_path / region_path).resolve()
    base = data_path.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid region path")
    if resolved == base:
        raise HTTPException(status_code=400, detail="Invalid region path")
    if not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Region directory not found")
    return resolved


def _label_for_region_path(region_path: str) -> str:
    parts = region_path.replace("\\", "/").rstrip("/").split("/")
    if len(parts) >= 2 and parts[-1] == "region":
        if parts[-2] == "DIM-1":
            return "Nether"
        if parts[-2] == "DIM1":
            return "End"
    if region_path.endswith("/region") or region_path == "region":
        return "Overworld"
    return region_path


def _discover_dimensions(data_path: Path) -> List[DimensionInfo]:
    cache_dir_name = ".mcmap"
    results: List[DimensionInfo] = []
    if not data_path.is_dir():
        return results

    def walk(d: Path) -> None:
        try:
            entries = list(d.iterdir())
        except (PermissionError, OSError):
            return
        # Only directories named exactly "region" hold the renderable terrain
        # MCAs. Sibling folders like "entities" and "poi" also contain
        # r.X.Z.mca files but represent entity/POI data, not the world map.
        if d.name == "region":
            mca_count = sum(
                1
                for entry in entries
                if entry.is_file() and REGION_FILE_RE.match(entry.name)
            )
            if mca_count > 0:
                rel = d.relative_to(data_path).as_posix()
                results.append(
                    DimensionInfo(
                        region_path=rel,
                        label=_label_for_region_path(rel),
                        mca_count=mca_count,
                    )
                )
            return
        for entry in entries:
            if entry.is_dir() and entry.name != cache_dir_name:
                walk(entry)

    walk(data_path)
    results.sort(key=lambda d: d.region_path)
    return results


def _list_regions(region_dir: Path) -> List[Tuple[int, int, int]]:
    # Each entry is `(x, z, mtime)`. The mtime is the MCA file's mtime in
    # whole epoch seconds; the frontend appends it as `?mt=` on tile URLs so
    # the browser HTTP cache busts automatically on regeneration.
    coords: List[Tuple[int, int, int]] = []
    try:
        entries = list(region_dir.iterdir())
    except (PermissionError, OSError):
        return coords
    for entry in entries:
        m = REGION_FILE_RE.match(entry.name)
        if not m:
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        # Skip zero-byte MCAs: fastanvil cannot parse them, mcmap reports
        # `UnexpectedEof` and the tile would never render. Excluding them from
        # the manifest lets the frontend short-circuit to a blank tile without
        # an HTTP round-trip.
        if not entry.is_file() or st.st_size == 0:
            continue
        coords.append((int(m.group(1)), int(m.group(2)), int(st.st_mtime)))
    coords.sort()
    return coords


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
        mods_dir = discover_mods_dir(data_path)
        try:
            palette_current = palette_is_current(cache, version, mods_dir)
        except OSError:
            palette_current = False

    return MapStatus(
        client_jar_present=cache.client_jar.exists(),
        palette_present=cache.palette_json.exists(),
        palette_current=palette_current,
        version=version,
    )


@router.get("/{server_id}/map/dimensions", response_model=List[DimensionInfo])
async def get_dimensions(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> List[DimensionInfo]:
    data_path = await _get_data_path(server_id)
    return _discover_dimensions(data_path)


# Region manifest: list of (x, z, mtime) triples for every r.X.Z.mca in the
# dimension. Frontend uses this to (1) skip HTTP requests for non-existent
# tiles and (2) append the mtime to each tile URL so the browser HTTP cache
# busts automatically when the MCA changes.
@router.get("/{server_id}/map/regions", response_model=List[Tuple[int, int, int]])
async def get_regions(
    server_id: str,
    region: str = Query(..., description="Region folder relative to data/"),
    _: UserPublic = Depends(get_current_user),
) -> List[Tuple[int, int, int]]:
    data_path = await _get_data_path(server_id)
    region_dir = _resolve_region_path(data_path, region)
    return _list_regions(region_dir)


def _sse(event_obj: dict) -> bytes:
    return f"data: {json.dumps(event_obj, separators=(',', ':'))}\n\n".encode()


async def _initialize_stream(
    server_id: str,
) -> AsyncGenerator[bytes, None]:
    instance = docker_mc_manager.get_instance(server_id)
    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)
    cache.ensure_dir(cache.cache_dir)

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
    if cache.client_jar.exists():
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
    mods_dir = discover_mods_dir(data_path)
    if palette_is_current(cache, version, mods_dir):
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

    try:
        async with mcmap_runner.gen_palette_modern(
            packs, cache.palette_json, owned_by=data_path
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
                    write_palette_hash(cache, version, mods_dir)
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

    if not cache.palette_json.exists():
        raise HTTPException(
            status_code=409, detail="Map not initialized — call /initialize first"
        )

    _resolve_region_path(data_path, region)
    cfg = config.mcmap

    state = cache.is_fresh(region, x, z, cfg.stale_timeout_seconds)
    if state == "missing_mca":
        raise HTTPException(status_code=404, detail="Region not present")
    if state == "fresh":
        return _png_response(cache.png_path(region, x, z))

    queue = await mcmap_manager.get_queue(server_id, region, cache)
    try:
        png = await asyncio.wait_for(
            queue.request(x, z), timeout=cfg.request_timeout_seconds
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Render timed out, retry")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Region not present")
    return _png_response(png)


def _png_response(png: Path) -> FileResponse:
    # Tile URLs carry the source MCA's mtime as `?mt=`, so any regeneration
    # produces a new URL; the cached response can sit forever (`max-age=1y`)
    # without going stale. `private` keeps it out of shared proxies — the
    # response body is gated by per-user JWT — and `Vary: Authorization`
    # prevents one user's cached response from being reused under a different
    # token. ETag stays as a fallback for the hard-reload (revalidate) path.
    return FileResponse(
        str(png),
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=31536000",
            "Vary": "Authorization",
            "ETag": f'"{int(png.stat().st_mtime)}"',
        },
    )


@router.delete("/{server_id}/map/cache")
async def clear_dimension_cache(
    server_id: str,
    region: str = Query(..., description="Region folder relative to data/"),
    _: UserPublic = Depends(get_current_user),
) -> dict:
    data_path = await _get_data_path(server_id)
    _resolve_region_path(data_path, region)
    cache = ServerMapCache(data_path=data_path)
    tiles = cache.tiles_dir(region)
    if tiles.exists():
        shutil.rmtree(tiles)
    return {"cleared": region}
