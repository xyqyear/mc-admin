import os
import posixpath
from pathlib import Path

from ..grid_geometry import build_grid_shapes
from ..world.region_files import parse_region_filename
from .models import (
    ChunkPrunePreviewGeometryResponse,
    ChunkPruneTaskMetadata,
    GridGeometryDimension,
    GridShape,
)


def build_preview_geometry(
    metadata: ChunkPruneTaskMetadata,
    selected_cells_by_dimension: dict[str, set[tuple[int, int]]],
) -> ChunkPrunePreviewGeometryResponse:
    unit = "chunk" if metadata.mode == "chunks" else "region"
    dimensions: list[GridGeometryDimension] = []
    for relpath, cells in sorted(selected_cells_by_dimension.items()):
        shapes = [
            GridShape(
                id=shape.id,
                cell_count=shape.cell_count,
                bbox=shape.bbox,
                rings=shape.rings,
            )
            for shape in build_grid_shapes(cells, id_prefix=relpath)
        ]
        dimensions.append(
            GridGeometryDimension(
                region_dir_relpath=relpath,
                unit=unit,
                cell_count=len(cells),
                shapes=shapes,
            )
        )
    return ChunkPrunePreviewGeometryResponse(
        task_id=metadata.task_id,
        server_id=metadata.server_id,
        mode=metadata.mode,
        threshold_seconds=metadata.threshold_seconds,
        threshold_ticks=metadata.threshold_ticks,
        dimensions=dimensions,
    )

class PruneEventPathMapper:
    def __init__(self, data_path: Path) -> None:
        self._data_root = normalize_event_path(os.path.abspath(os.fspath(data_path)))

    def region_relpath(self, event_region: str) -> str | None:
        event_path = normalize_event_path(event_region)
        if not event_path or event_path == ".":
            return None

        if event_path.startswith("/"):
            prefix = f"{self._data_root}/"
            if event_path == self._data_root or not event_path.startswith(prefix):
                return None
            relpath = event_path[len(prefix) :]
        else:
            relpath = event_path

        parts = relpath.split("/")
        if (
            len(parts) < 3
            or any(part in ("", ".", "..") for part in parts)
            or parts[-2] != "region"
            or parse_region_filename(parts[-1]) is None
        ):
            return None
        return "/".join(parts[:-1])

def normalize_event_path(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))

def region_relpath_for_event(data_path: Path, event_region: str) -> str | None:
    return PruneEventPathMapper(data_path).region_relpath(event_region)
