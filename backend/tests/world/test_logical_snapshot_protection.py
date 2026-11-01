from pathlib import Path

import pytest

from app.snapshots.restoration_models import RestorationType
from app.snapshots.selection_models import RestorationSelection
from app.world.events import SelectionResolutionError
from app.world.selection import resolve_paths


@pytest.mark.parametrize("escaped_kind", ["region", "mca", "mcc"])
async def test_world_selection_rejects_external_targets(
    tmp_path: Path, escaped_kind,
):
    data = tmp_path / "data"
    region = data / "world" / "region"
    region.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / ("c.0.0.mcc" if escaped_kind == "mcc" else "r.0.0.mca")
    external.write_bytes(b"unmanaged content")
    if escaped_kind == "region":
        region.rmdir()
        region.symlink_to(outside, target_is_directory=True)
    else:
        (region / external.name).symlink_to(external)

    with pytest.raises(SelectionResolutionError):
        await resolve_paths(
            data, RestorationSelection(type=RestorationType.CHUNKS,
                region_dir_relpath="world/region", chunks=[(0, 0)]),
            include_mcc=True, allow_missing_dimension=True,
        )

    assert external.read_bytes() == b"unmanaged content"
