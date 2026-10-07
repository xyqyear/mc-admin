from pathlib import Path

import pytest

from app.snapshots.protection import SnapshotProtection
from app.utils.async_fs import PathOutsideBaseError
from app.world.scope_execution import RestoreScopeExecutor


@pytest.mark.parametrize("ignored_name", ["world", "world_alias"])
async def test_chunk_selection_uses_the_selected_world_name(tmp_path, ignored_name):
    data = tmp_path / "data"
    region = data / "world" / "region"
    region.mkdir(parents=True)
    (region / "r.0.0.mca").write_bytes(b"live terrain")
    (data / "world_alias").symlink_to(region.parent, target_is_directory=True)
    protection = SnapshotProtection.capture([data / ignored_name / "region"])

    allowed = await RestoreScopeExecutor.allowed_chunks(
        data, data / "world_alias" / "region" / "r.0.0.mca", 0, 0,
        [(0, 0), (1, 0)], protection,
    )

    assert allowed == ([(0, 0), (1, 0)] if ignored_name == "world" else [])
    assert (region / "r.0.0.mca").read_bytes() == b"live terrain"


@pytest.mark.parametrize("ignored_name", ["world", "world_alias"])
async def test_mcc_rule_preserves_its_chunk_only_for_the_selected_name(
    tmp_path, ignored_name,
):
    data = tmp_path / "data"
    region = data / "world" / "region"
    region.mkdir(parents=True)
    (region / "r.0.0.mca").write_bytes(b"live terrain")
    (region / "c.0.0.mcc").write_bytes(b"live overflow")
    (data / "world_alias").symlink_to(region.parent, target_is_directory=True)
    protection = SnapshotProtection.capture(
        [data / ignored_name / "region" / "c.0.0.mcc"]
    )

    allowed = await RestoreScopeExecutor.allowed_chunks(
        data, data / "world_alias" / "region" / "r.0.0.mca", 0, 0,
        [(0, 0), (1, 0)], protection,
    )

    assert allowed == ([(0, 0), (1, 0)] if ignored_name == "world" else [(1, 0)])
    assert (region / "c.0.0.mcc").read_bytes() == b"live overflow"


@pytest.mark.parametrize("escaped_kind", ["region", "mca", "mcc"])
async def test_logical_chunk_rules_do_not_allow_external_targets(
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

    with pytest.raises(PathOutsideBaseError):
        await RestoreScopeExecutor.allowed_chunks(
            data, region / "r.0.0.mca", 0, 0, [(0, 0)],
            SnapshotProtection.capture([]),
        )

    assert external.read_bytes() == b"unmanaged content"
