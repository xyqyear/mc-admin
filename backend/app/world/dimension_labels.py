from pathlib import Path

from ..dynamic_config import config
from ..dynamic_config.configs.world import (
    DIMENSION_LABELS,
    END_LABEL,
    NETHER_LABEL,
    OVERWORLD_LABEL,
)

DIMENSIONS_PREFIX = "dimensions/"


def dimension_path_for_dir(world_root: Path, dimension_dir: Path) -> str:
    return dimension_dir.relative_to(world_root).as_posix()


def label_for_dimension_path(dimension_path: str) -> str:
    return config.world.dimension_labels.get(
        dimension_path, dimension_path.removeprefix(DIMENSIONS_PREFIX)
    )


def label_for_dimension_dir(world_root: Path, dimension_dir: Path) -> str:
    return label_for_dimension_path(dimension_path_for_dir(world_root, dimension_dir))
