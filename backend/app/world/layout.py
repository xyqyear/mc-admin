"""World root + dimension discovery; supports vanilla and Bukkit/Paper multi-world layouts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os as aioos

from ..minecraft.properties import ServerProperties

DEFAULT_LEVEL_NAME = "world"
NETHER_DIR = "DIM-1"
END_DIR = "DIM1"
OVERWORLD_LABEL = "Overworld"
NETHER_LABEL = "Nether"
END_LABEL = "End"
MCMAP_DIR_NAME = ".mcmap"


@dataclass(frozen=True)
class DimensionInfo:
    region_dir: Path
    entities_dir: Optional[Path]
    poi_dir: Optional[Path]
    label: str


@dataclass(frozen=True)
class WorldRoot:
    name: str
    path: Path
    dimensions: list[DimensionInfo]


async def _read_level_name(data_path: Path) -> str:
    """Resolve `level-name` from server.properties; fall back to "world"."""
    properties_path = data_path / "server.properties"
    if not await aioos.path.exists(properties_path):
        return DEFAULT_LEVEL_NAME
    try:
        async with aiofiles.open(properties_path) as f:
            content = await f.read()
    except OSError:
        return DEFAULT_LEVEL_NAME
    parsed = ServerProperties.from_server_properties(content)
    if parsed.level_name and parsed.level_name.strip():
        return parsed.level_name.strip()
    return DEFAULT_LEVEL_NAME


async def _has_level_dat(directory: Path) -> bool:
    return await aioos.path.isfile(directory / "level.dat")


async def _has_region_mca(region_dir: Path) -> bool:
    """True if `region_dir` exists and contains at least one r.X.Z.mca file."""
    if not await aioos.path.isdir(region_dir):
        return False
    try:
        entries = await aioos.listdir(region_dir)
    except OSError:
        return False
    for entry in entries:
        if entry.startswith("r.") and entry.endswith(".mca"):
            return True
    return False


def _label_for_dimension(world_root: Path, region_parent: Path) -> str:
    """Map a dimension's region-parent dir to a human-readable label."""
    if region_parent == world_root:
        return OVERWORLD_LABEL
    name = region_parent.name
    if name == NETHER_DIR:
        return NETHER_LABEL
    if name == END_DIR:
        return END_LABEL
    return name


async def _discover_dimensions(world_root: Path) -> list[DimensionInfo]:
    """A dimension is a dir whose ``region/`` holds at least one ``r.X.Z.mca``.

    Checks the root itself (Overworld) plus one level of children (DIM-1, DIM1, custom).
    """
    candidates: list[Path] = [world_root]
    try:
        entries = await aioos.listdir(world_root)
    except OSError:
        entries = []
    for entry in sorted(entries):
        if entry == MCMAP_DIR_NAME:
            continue
        child = world_root / entry
        if await aioos.path.isdir(child):
            candidates.append(child)

    dimensions: list[DimensionInfo] = []
    for parent in candidates:
        region_dir = parent / "region"
        if not await _has_region_mca(region_dir):
            continue
        entities_dir = parent / "entities"
        poi_dir = parent / "poi"
        dimensions.append(
            DimensionInfo(
                region_dir=region_dir,
                entities_dir=entities_dir if await aioos.path.isdir(entities_dir) else None,
                poi_dir=poi_dir if await aioos.path.isdir(poi_dir) else None,
                label=_label_for_dimension(world_root, parent),
            )
        )
    dimensions.sort(key=lambda d: d.label)
    return dimensions


async def discover_world_roots(data_path: Path) -> list[WorldRoot]:
    """Find world roots under ``data_path``: primary from ``level-name`` plus peers with ``level.dat``."""
    if not await aioos.path.isdir(data_path):
        return []

    level_name = await _read_level_name(data_path)
    primary_path = data_path / level_name
    if not await aioos.path.isdir(primary_path):
        primary_path = data_path / DEFAULT_LEVEL_NAME

    candidate_names: set[str] = set()
    if await aioos.path.isdir(primary_path):
        candidate_names.add(primary_path.name)

    try:
        entries = await aioos.listdir(data_path)
    except OSError:
        entries = []
    for entry in entries:
        if entry == MCMAP_DIR_NAME:
            continue
        child = data_path / entry
        if not await aioos.path.isdir(child):
            continue
        if await _has_level_dat(child):
            candidate_names.add(entry)

    roots: list[WorldRoot] = []
    for name in sorted(candidate_names):
        root_path = data_path / name
        dimensions = await _discover_dimensions(root_path)
        if not dimensions:
            continue
        roots.append(WorldRoot(name=name, path=root_path, dimensions=dimensions))
    return roots
