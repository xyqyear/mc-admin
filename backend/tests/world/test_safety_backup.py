import pytest

from app.snapshots.restoration_models import RestorationType
from app.snapshots.selection_models import RestorationSelection
from app.world.events import SelectionResolutionError
from app.world.selection import resolve_paths


@pytest.mark.parametrize(
    "relative", ["../outside", "/tmp/outside", ".", "world/../other/region"]
)
async def test_history_missing_dimension_rejects_unconfined_paths(tmp_path, relative):
    selection = RestorationSelection(
        type=RestorationType.DIMENSION, region_dir_relpath=relative
    )
    with pytest.raises(SelectionResolutionError):
        await resolve_paths(
            tmp_path, selection, include_mcc=True, allow_missing_dimension=True
        )


async def test_history_missing_dimension_rejects_external_symlink(tmp_path):
    data = tmp_path / "data"
    outside = tmp_path / "outside"
    data.mkdir()
    outside.mkdir()
    (data / "world").symlink_to(outside, target_is_directory=True)
    selection = RestorationSelection(
        type=RestorationType.REGIONS,
        region_dir_relpath="world/region",
        regions=[(0, 0)],
    )
    with pytest.raises(SelectionResolutionError):
        await resolve_paths(
            data, selection, include_mcc=True, allow_missing_dimension=True
        )
