"""Map-tile cache invalidation for world-restore flows.

After a restore mutates region MCAs on disk, the cached PNG tiles under
``data/.mcmap/tiles/<region_path>/r.X.Z.png`` are stale. This module computes
which tile files need to be removed and deletes them; the next tile request
hits ``ServerMapCache.is_fresh`` returning ``"missing_png"`` and re-renders.

Two entry points:

* :func:`pngs_for_restic_items` — derives affected tiles from an iterable of
  absolute paths (typically the ``item`` values of restic's ``verbose_status``
  events with ``action`` ∈ {updated, restored, deleted}). Works across
  arbitrary world-root layouts because the cache key for a tile is just the
  parent dir's relpath under ``data_path``.

* :func:`pngs_for_regions` — derives tiles from a known set of (rx, rz)
  region coordinates plus the dimension's ``region_dir_relpath``. Used when
  the orchestrator already knows which regions were touched (REGIONS scope
  via ``selection.regions``, CHUNKS scope via ``selection.chunks`` grouped to
  regions).

Only files under ``<root>/[<dim>/]region/r.X.Z.mca`` are considered. Entities
and POI MCAs have no rendered tile, so they're skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ..mcmap.cache import ServerMapCache

_MCA_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


def _png_for_region_mca(data_path: Path, mca_path: Path) -> Path | None:
    """Resolve a region MCA path to its cached PNG path, or None if it's not
    a region MCA living under ``data_path``.

    Skips entities/poi MCAs (parent dir name != "region") since those don't
    have rendered tiles.
    """
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
    """Map a stream of restic file-action ``item`` paths to PNG tile paths.

    Items not under ``data_path`` or that don't name a region MCA are
    silently ignored. The returned set is deduplicated.
    """
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
    """Compute PNG paths for an explicit set of regions in one dimension.

    ``region_dir_relpath`` is the dimension's data-relative region dir
    (e.g. ``"world/region"`` or ``"world/DIM-1/region"``). The cache key is
    that same relpath, so the lookup is a direct call to
    ``ServerMapCache.png_path``.
    """
    cache = ServerMapCache(data_path=data_path)
    return {cache.png_path(region_dir_relpath, rx, rz) for rx, rz in regions}


def delete_pngs(pngs: Iterable[Path]) -> int:
    """Best-effort delete the given PNG files. Returns count actually removed."""
    removed = 0
    for png in pngs:
        try:
            png.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return removed
