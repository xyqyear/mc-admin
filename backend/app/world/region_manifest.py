import asyncio
import os
import stat as _stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..dynamic_config import config
from .region_files import parse_region_filename


async def list_region_manifest(region_dir: Path) -> list[tuple[int, int, int]]:
    return await asyncio.to_thread(list_region_manifest_sync, region_dir)


def list_region_manifest_sync(region_dir: Path) -> list[tuple[int, int, int]]:
    # (x, z, mtime); mtime feeds tile URL `?mt=` for cache busting.
    candidates: list[tuple[str, int, int]] = []
    try:
        entries = os.scandir(region_dir)
    except (PermissionError, OSError):
        return []
    with entries:
        for entry in entries:
            parsed = parse_region_filename(entry.name)
            if parsed is None:
                continue
            x, z = parsed
            candidates.append((entry.path, x, z))

    rows: list[tuple[int, int, int]] = []
    workers = min(config.world.region_stat_workers, len(candidates))
    if workers <= 1:
        for candidate in candidates:
            coord = _stat_region_candidate(candidate)
            if coord is not None:
                rows.append(coord)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for coord in pool.map(_stat_region_candidate, candidates):
                if coord is not None:
                    rows.append(coord)
    rows.sort()
    return rows


def _stat_region_candidate(
    candidate: tuple[str, int, int],
) -> tuple[int, int, int] | None:
    path, x, z = candidate
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    if not _stat.S_ISREG(st.st_mode) or st.st_size == 0:
        return None
    return (x, z, int(st.st_mtime))
