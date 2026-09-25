import asyncio
from collections.abc import Iterable
from pathlib import Path

import aiofiles.os as aioos

from app.world.models import RestorationType
from app.world.schemas import RestorationSelection

from ..utils import async_fs
from .events import SelectionResolutionError
from .layout import DimensionInfo, WorldRoot, discover_world_roots

CHUNKS_PER_REGION_AXIS = 32
SUBDIR_KINDS = ("region", "entities", "poi")
RESTORATION_TYPE_LABELS = {
    RestorationType.WORLD: "整个世界", RestorationType.DIMENSION: "维度",
    RestorationType.REGIONS: "区域", RestorationType.CHUNKS: "区块",
}

def _selection_label(selection: RestorationSelection) -> str:
    return RESTORATION_TYPE_LABELS.get(selection.type, selection.type.value)


def _group_chunks_by_region(
    chunks: Iterable[tuple[int, int]],
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Group absolute ``(cx, cz)`` by region; values are region-relative ``0..31`` coords."""
    grouped: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for cx, cz in chunks:
        rx = cx // CHUNKS_PER_REGION_AXIS
        rz = cz // CHUNKS_PER_REGION_AXIS
        local_x = cx % CHUNKS_PER_REGION_AXIS
        local_z = cz % CHUNKS_PER_REGION_AXIS
        grouped.setdefault((rx, rz), []).append((local_x, local_z))
    return grouped


def _mcc_paths_for_region(
    region_dir: Path, rx: int, rz: int
) -> list[Path]:
    """Speculative ``c.<absX>.<absZ>.mcc`` paths; restic ignores ones that don't exist."""
    paths: list[Path] = []
    base_x = rx * CHUNKS_PER_REGION_AXIS
    base_z = rz * CHUNKS_PER_REGION_AXIS
    for dx in range(CHUNKS_PER_REGION_AXIS):
        for dz in range(CHUNKS_PER_REGION_AXIS):
            paths.append(region_dir / f"c.{base_x + dx}.{base_z + dz}.mcc")
    return paths


def _restore_dimension(dim: DimensionInfo) -> DimensionInfo:
    return DimensionInfo(
        region_dir=dim.region_dir,
        entities_dir=dim.region_dir.parent / "entities",
        poi_dir=dim.region_dir.parent / "poi",
    )


def _find_dimension(
    data_path: Path,
    roots: list[WorldRoot],
    region_dir_relpath: str,
) -> DimensionInfo:
    """Locate a dimension across all world roots by its data-relative path."""
    target = Path(region_dir_relpath)
    for root in roots:
        for dim in root.dimensions:
            try:
                if dim.region_dir.relative_to(data_path) == target:
                    return dim
            except ValueError:
                continue
    raise SelectionResolutionError(
        f"未找到维度路径 '{region_dir_relpath}'"
    )


def _expand_region_paths(
    dim: DimensionInfo, regions: list[tuple[int, int]]
) -> list[Path]:
    """Include-path list (MCA + speculative MCCs) for regions/chunks restores."""
    paths: list[Path] = []
    for (rx, rz) in regions:
        for live_dir in (dim.region_dir, dim.entities_dir, dim.poi_dir):
            if live_dir is None:
                continue
            paths.append(live_dir / f"r.{rx}.{rz}.mca")
            paths.extend(_mcc_paths_for_region(live_dir, rx, rz))
    return paths


def _expand_region_mca_paths(
    dim: DimensionInfo, regions: list[tuple[int, int]]
) -> list[Path]:
    """MCA-only variant; speculative MCC sidecars would over-filter eligibility checks."""
    paths: list[Path] = []
    for (rx, rz) in regions:
        for live_dir in (dim.region_dir, dim.entities_dir, dim.poi_dir):
            if live_dir is None:
                continue
            paths.append(live_dir / f"r.{rx}.{rz}.mca")
    return paths


def _count_affected_regions(selection: RestorationSelection) -> int:
    """Disk-guard heuristic used by ``PreviewSessionManager``."""
    if selection.type is RestorationType.REGIONS:
        return len(selection.regions)
    if selection.type is RestorationType.CHUNKS:
        return len({(c[0] // CHUNKS_PER_REGION_AXIS, c[1] // CHUNKS_PER_REGION_AXIS) for c in selection.chunks})
    # WORLD/DIMENSION counts require a disk scan; use a conservative default to avoid false trips.
    return 16


async def _plan_paths(
    data_path: Path,
    selection: RestorationSelection,
    *,
    include_mcc: bool,
    include_missing: bool = False,
    allow_missing_dimension: bool = False,
    world_roots: list[str] | None = None,
) -> list[Path]:
    if selection.type is RestorationType.WORLD and world_roots is not None:
        return [await confined_history_path(data_path, value) for value in world_roots]
    roots = [] if allow_missing_dimension else await discover_world_roots(data_path)

    if selection.type is RestorationType.WORLD:
        return [root.path for root in roots]

    if selection.region_dir_relpath is None:
        raise SelectionResolutionError(
            f"{_selection_label(selection)}选择范围需要指定维度路径"
        )
    dim = await resolve_dimension(data_path, selection.region_dir_relpath, allow_missing=allow_missing_dimension, roots=roots)
    if include_missing:
        dim = _restore_dimension(dim)

    if selection.type is RestorationType.DIMENSION:
        paths = [dim.region_dir]
        if dim.entities_dir is not None:
            paths.append(dim.entities_dir)
        if dim.poi_dir is not None:
            paths.append(dim.poi_dir)
        return paths

    expand = _expand_region_paths if include_mcc else _expand_region_mca_paths

    if selection.type is RestorationType.REGIONS:
        return expand(dim, selection.regions)

    if selection.type is RestorationType.CHUNKS:
        grouped = _group_chunks_by_region(selection.chunks)
        return expand(dim, list(grouped.keys()))

    raise SelectionResolutionError(f"不支持的选择范围类型: {selection.type}")


async def resource_scopes(data_path: Path, paths: list[Path]) -> list[Path]:
    def resolve() -> list[Path]:
        root = data_path.resolve()
        scopes: set[Path] = set()
        resolved_directories: dict[Path, Path] = {}
        for path in paths:
            directory = path.parent if path.suffix in {".mca", ".mcc"} else path
            if directory not in resolved_directories:
                resolved_directories[directory] = directory.resolve()
            resolved = resolved_directories[directory]
            if not resolved.is_relative_to(root):
                raise SelectionResolutionError("世界选择范围超出服务器数据目录，请检查符号链接")
            scopes.update((directory, resolved))
            if path != directory and path.is_symlink():
                target = path.resolve()
                if not target.is_relative_to(root):
                    raise SelectionResolutionError("世界文件超出服务器数据目录，请检查符号链接")
                scopes.add(target)
        return sorted(scopes)

    return await asyncio.to_thread(resolve)


async def resolve_paths(
    data_path: Path, selection: RestorationSelection, *, include_mcc: bool, include_missing: bool = False,
    allow_missing_dimension: bool = False, world_roots: list[str] | None = None,
) -> list[Path]:
    paths = await _plan_paths(data_path, selection, include_mcc=include_mcc, include_missing=include_missing,
                              allow_missing_dimension=allow_missing_dimension, world_roots=world_roots)
    await resource_scopes(data_path, paths)
    return paths


async def confined_history_path(data_path: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise SelectionResolutionError("恢复记录中的路径不属于服务器数据目录")
    try:
        await async_fs.resolve_inside(data_path, data_path / path)
    except async_fs.PathOutsideBaseError as exc:
        raise SelectionResolutionError("恢复记录中的路径超出服务器数据目录") from exc
    return data_path / path


async def resolve_dimension(
    data_path: Path, relative: str, *, allow_missing: bool = False, roots: list[WorldRoot] | None = None,
) -> DimensionInfo:
    region = await confined_history_path(data_path, relative)
    if region.name != "region":
        raise SelectionResolutionError("恢复记录中的维度路径必须指向 region 目录")
    if allow_missing:
        return _restore_dimension(DimensionInfo(region, None, None))
    return _find_dimension(data_path, roots if roots is not None else await discover_world_roots(data_path), relative)


def selection_directories(paths: list[Path], selection: RestorationSelection) -> list[Path]:
    if selection.type in (RestorationType.REGIONS, RestorationType.CHUNKS):
        return sorted({path.parent for path in paths})
    return paths


async def absent_directories(data_path: Path, paths: list[Path], selection: RestorationSelection) -> list[str]:
    absent: set[str] = set()
    for directory in selection_directories(paths, selection):
        while directory != data_path and not await aioos.path.exists(directory):
            relative = directory.relative_to(data_path).as_posix()
            await confined_history_path(data_path, relative)
            absent.add(relative)
            directory = directory.parent
    return sorted(absent)


async def absent_sidecar_dirs(
    data_path: Path, selection: RestorationSelection
) -> list[str]:
    if selection.type is RestorationType.WORLD or not selection.region_dir_relpath:
        return []
    dimension = data_path / selection.region_dir_relpath
    return [
        (dimension.parent / kind).relative_to(data_path).as_posix()
        for kind in ("entities", "poi")
        if not await aioos.path.exists(dimension.parent / kind)
    ]
