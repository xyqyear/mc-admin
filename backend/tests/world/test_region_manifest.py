import os

import pytest

from app.world.region_manifest import list_region_manifest_sync


@pytest.mark.parametrize("workers", [1, 3])
def test_region_manifest_preserves_complete_current_files(tmp_path, runtime_config, workers):
    runtime_config.world.region_stat_workers = workers
    for name in ("r.-1.2.mca", "r.3.0.mca", "r.0.0.mca"):
        path = tmp_path / name
        path.write_bytes(b"region content")
        os.utime(path, (1_700_000_000, 1_700_000_000))
    (tmp_path / "r.99.99.mca").mkdir()
    (tmp_path / "r.5.5.mca").touch()
    (tmp_path / "not-a-region.mca").write_bytes(b"unrelated")

    assert list_region_manifest_sync(tmp_path) == [
        (-1, 2, 1_700_000_000), (0, 0, 1_700_000_000), (3, 0, 1_700_000_000),
    ]
    (tmp_path / "r.0.0.mca").unlink()
    assert list_region_manifest_sync(tmp_path) == [
        (-1, 2, 1_700_000_000), (3, 0, 1_700_000_000),
    ]
