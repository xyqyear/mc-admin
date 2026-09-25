from pathlib import Path

from app.world.models import RestorationType
from app.world.schemas import RestorationSelection

from ..mcmap.cache import ServerMapCache
from ..utils import async_fs
from .selection import _group_chunks_by_region


async def invalidate_map_cache(
    *,
    data_path: Path,
    selection: RestorationSelection,
    touched_items: list[str],
    uncertain: bool = False,
) -> int:
    """Drop cached PNG tiles whose source MCA changed.

    WORLD/DIMENSION derives affected regions from ``touched_items``
    (restic verbose_status); REGIONS/CHUNKS uses the selection directly
    as the source of truth.
    """
    from . import png_invalidate

    if uncertain and selection.type in {RestorationType.WORLD, RestorationType.DIMENSION}:
        cache = ServerMapCache(data_path)
        tiles = cache.tiles_dir(selection.region_dir_relpath or "")
        await async_fs.resolve_inside(data_path, tiles)
        try:
            await async_fs.rmtree(tiles)
        except FileNotFoundError:
            pass
        return 0

    if selection.type in (RestorationType.WORLD, RestorationType.DIMENSION):
        pngs = png_invalidate.pngs_for_restic_items(data_path, touched_items)
    elif selection.type is RestorationType.REGIONS:
        if selection.region_dir_relpath is None:
            return 0
        pngs = png_invalidate.pngs_for_regions(
            data_path, selection.region_dir_relpath, set(selection.regions)
        )
    elif selection.type is RestorationType.CHUNKS:
        if selection.region_dir_relpath is None:
            return 0
        grouped = _group_chunks_by_region(selection.chunks)
        pngs = png_invalidate.pngs_for_regions(
            data_path, selection.region_dir_relpath, set(grouped.keys())
        )
    else:
        return 0

    if not pngs:
        return 0
    return await png_invalidate.delete_pngs(pngs, data_path=data_path)
