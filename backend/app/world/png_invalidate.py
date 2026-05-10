"""Map-tile cache invalidation for world-restore flows.

Two entry points: ``pngs_for_restic_items`` (from restic verbose_status item
paths) and ``pngs_for_regions`` (from explicit ``(rx, rz)`` coords). Only
``region/`` MCAs map to PNGs; entities/POI MCAs are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import aiofiles.os as aioos

from ..logger import logger
from ..mcmap.cache import ServerMapCache

_MCA_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


def _png_for_region_mca(data_path: Path, mca_path: Path) -> Path | None:
    """PNG path for a region MCA under ``data_path``; ``None`` for entities/POI/non-MCA."""
    try:
        rel = mca_path.relative_to(data_path)
    except ValueError:
        return None
    m = _MCA_RE.match(rel.name)
    if m is None:
        return None
    if rel.parent.name != "region":
        return None
    x, z = int(m.group(1)), int(m.group(2))
    cache = ServerMapCache(data_path=data_path)
    return cache.png_path(str(rel.parent), x, z)


def pngs_for_restic_items(
    data_path: Path, items: Iterable[str | Path]
) -> set[Path]:
    """Filter restic ``item`` paths to PNG tile paths; ignore items outside ``data_path``."""
    out: set[Path] = set()
    for raw in items:
        png = _png_for_region_mca(data_path, Path(raw))
        if png is not None:
            out.add(png)
    return out


def pngs_for_regions(
    data_path: Path,
    region_dir_relpath: str,
    regions: Iterable[tuple[int, int]],
) -> set[Path]:
    """PNG paths for ``(rx, rz)`` coords in the dimension named by ``region_dir_relpath``."""
    cache = ServerMapCache(data_path=data_path)
    return {cache.png_path(region_dir_relpath, rx, rz) for rx, rz in regions}


async def delete_pngs(pngs: Iterable[Path]) -> int:
    """Best-effort delete the given PNG files. Returns count actually removed."""
    removed = 0
    for png in pngs:
        try:
            await aioos.unlink(png)
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("failed to delete tile %s", png, exc_info=True)
            continue
    return removed
