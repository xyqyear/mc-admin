from pathlib import Path

OVERWORLD_LABEL = "Overworld"
NETHER_LABEL = "Nether"
END_LABEL = "End"
DIMENSIONS_PREFIX = "dimensions/"
VANILLA_DIMENSION_LABELS = {
    ".": OVERWORLD_LABEL,
    "DIM-1": NETHER_LABEL,
    "DIM1": END_LABEL,
    "dimensions/minecraft/overworld": OVERWORLD_LABEL,
    "dimensions/minecraft/the_nether": NETHER_LABEL,
    "dimensions/minecraft/the_end": END_LABEL,
}


def label_for_dimension_dir(world_root: Path, dimension_dir: Path) -> str:
    rel = dimension_dir.relative_to(world_root).as_posix()
    return VANILLA_DIMENSION_LABELS.get(rel, rel.removeprefix(DIMENSIONS_PREFIX))
