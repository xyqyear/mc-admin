import asyncio
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from ..config import settings
from ..dynamic_config import config
from ..minecraft.properties import DEFAULT_LEVEL_NAME, read_level_name_sync
from .region_files import parse_region_filename


@dataclass(frozen=True)
class DimensionInfo:
    region_dir: Path
    entities_dir: Optional[Path]
    poi_dir: Optional[Path]


@dataclass(frozen=True)
class WorldRoot:
    name: str
    path: Path
    dimensions: list[DimensionInfo]


@dataclass(frozen=True)
class WorldRootPath:
    name: str
    path: Path


@dataclass(frozen=True)
class DimensionFolderResolution:
    region_dir_relpath: Optional[str]
    exists_on_disk: bool


class WorldLayoutDiscoveryError(RuntimeError):
    pass


def _has_level_dat_sync(directory: Path) -> bool:
    return (directory / "level.dat").is_file()


def _has_region_mca(region_dir: Path) -> bool:
    try:
        entries = os.scandir(region_dir)
    except OSError:
        return False
    with entries:
        for entry in entries:
            if parse_region_filename(entry.name) is None:
                continue
            try:
                if entry.is_file(follow_symlinks=False):
                    return True
            except OSError:
                continue
    return False


def _scandir_sorted(directory: Path) -> list[os.DirEntry[str]]:
    with os.scandir(directory) as entries:
        return sorted(entries, key=lambda e: e.name)


def _dimension_info(world_root: Path, directory: Path) -> Optional[DimensionInfo]:
    region_dir = directory / "region"
    if not _has_region_mca(region_dir):
        return None
    entities_dir = directory / "entities"
    poi_dir = directory / "poi"
    return DimensionInfo(
        region_dir=region_dir,
        entities_dir=entities_dir if entities_dir.is_dir() else None,
        poi_dir=poi_dir if poi_dir.is_dir() else None,
    )


def _world_root_paths_sync(data_path: Path) -> list[WorldRootPath]:
    if not data_path.is_dir():
        return []

    level_name = read_level_name_sync(data_path)
    primary_path = data_path / level_name
    if not primary_path.is_dir():
        primary_path = data_path / DEFAULT_LEVEL_NAME

    candidates: dict[str, Path] = {}
    if primary_path.is_dir():
        candidates[primary_path.name] = primary_path

    try:
        entries = _scandir_sorted(data_path)
    except OSError:
        entries = []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        child = Path(entry.path)
        if _has_level_dat_sync(child):
            candidates[entry.name] = child

    ordered: list[WorldRootPath] = []
    if primary_path.is_dir() and primary_path.name in candidates:
        ordered.append(WorldRootPath(primary_path.name, primary_path))
    for name in sorted(candidates):
        if primary_path.is_dir() and name == primary_path.name:
            continue
        ordered.append(WorldRootPath(name, candidates[name]))
    return ordered


def _dimension_folder_parts(folder: str) -> tuple[str, ...] | None:
    if folder in ("", "."):
        return ()
    normalized = PurePosixPath(folder.replace("\\", "/"))
    if normalized.is_absolute():
        return None
    parts = tuple(part for part in normalized.parts if part not in ("", "."))
    if any(part == ".." for part in parts):
        return None
    return parts


def resolve_dimension_folder(
    data_path: Path,
    world_root: WorldRootPath,
    folder: str,
    *,
    exists_on_disk: bool,
) -> DimensionFolderResolution:
    parts = _dimension_folder_parts(folder)
    if parts is None:
        return DimensionFolderResolution(
            region_dir_relpath=None,
            exists_on_disk=exists_on_disk,
        )

    dimension_dir = world_root.path.joinpath(*parts) if parts else world_root.path
    region_dir = dimension_dir / "region"
    has_region_mca = _has_region_mca(region_dir)
    relpath: Optional[str] = None
    if has_region_mca:
        try:
            relpath = region_dir.relative_to(data_path).as_posix()
        except ValueError:
            relpath = None
    return DimensionFolderResolution(
        region_dir_relpath=relpath,
        exists_on_disk=exists_on_disk or has_region_mca,
    )


def _dimensions_from_region_dirs_sync(
    world_root: Path, region_dirs: list[Path]
) -> list[DimensionInfo]:
    dimensions_by_dir: dict[Path, DimensionInfo] = {}
    for region_dir in region_dirs:
        if region_dir.name != "region":
            continue
        try:
            region_dir.relative_to(world_root)
        except ValueError:
            continue
        dimension_dir = region_dir.parent
        info = _dimension_info(world_root, dimension_dir)
        if info is not None:
            dimensions_by_dir[dimension_dir] = info

    dimensions = list(dimensions_by_dir.values())
    dimensions.sort(
        key=lambda d: (
            d.region_dir.parent != world_root,
            d.region_dir.parent.relative_to(world_root).as_posix(),
        )
    )
    return dimensions


async def _discover_region_dirs_with_fd(world_root: Path) -> list[Path]:
    region_dir_max_depth = config.world.dimension_max_depth_from_world_root + 1
    cmd = [
        str(settings.fd_binary_path),
        "--unrestricted",
        "--absolute-path",
        "--print0",
        "--case-sensitive",
        "--type",
        "directory",
        "--max-depth",
        str(region_dir_max_depth),
        "^region$",
        str(world_root),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise WorldLayoutDiscoveryError(
            f"fd command not found at {settings.fd_binary_path}; "
            "install fd or configure FD_BINARY_PATH"
        ) from None

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        raise WorldLayoutDiscoveryError(
            f"fd failed while discovering world layout under {world_root}: {detail}"
        )

    region_dirs: list[Path] = []
    for raw in stdout.split(b"\0"):
        if not raw:
            continue
        path = Path(os.fsdecode(raw))
        if not path.is_absolute():
            path = world_root / path
        region_dirs.append(path)
    return region_dirs


async def discover_world_roots(data_path: Path) -> list[WorldRoot]:
    candidates = await discover_world_root_paths(data_path)
    roots: list[WorldRoot] = []

    for candidate in candidates:
        region_dirs = await _discover_region_dirs_with_fd(candidate.path)
        dimensions = await asyncio.to_thread(
            _dimensions_from_region_dirs_sync, candidate.path, region_dirs
        )
        if not dimensions:
            continue
        roots.append(
            WorldRoot(name=candidate.name, path=candidate.path, dimensions=dimensions)
        )
    return roots


async def discover_world_root_paths(data_path: Path) -> list[WorldRootPath]:
    return await asyncio.to_thread(_world_root_paths_sync, data_path)
