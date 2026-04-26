"""Integrated tests for ResticManager.find_snapshots_covering using real restic."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from app.snapshots import ResticManager
from app.utils.exec import exec_command


def check_restic_available() -> bool:
    try:
        result = subprocess.run(
            ["restic", "version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(
    not check_restic_available(),
    reason="restic command not available - install restic to run these tests",
)


@pytest.fixture
def temp_repo_dir():
    with tempfile.TemporaryDirectory(prefix="restic_test_repo_cov_") as tmp:
        yield Path(tmp)


@pytest.fixture
def temp_data_dir():
    with tempfile.TemporaryDirectory(prefix="restic_test_data_cov_") as tmp:
        data = Path(tmp)
        # Build a synthetic minecraft layout
        (data / "world" / "region").mkdir(parents=True)
        (data / "world" / "region" / "r.0.0.mca").write_bytes(b"world-overworld-region")
        (data / "world" / "DIM-1" / "region").mkdir(parents=True)
        (data / "world" / "DIM-1" / "region" / "r.0.0.mca").write_bytes(
            b"world-nether-region"
        )
        (data / "other").mkdir(parents=True)
        (data / "other" / "file.txt").write_text("unrelated")
        yield data


@pytest.fixture
async def restic_manager(temp_repo_dir):
    manager = ResticManager(repository_path=str(temp_repo_dir), password=None)
    await exec_command("restic", "init", "--insecure-no-password", env=manager.env)
    return manager


@pytest.mark.asyncio
async def test_find_snapshots_covering_filters_by_and_coverage(
    restic_manager, temp_data_dir
):
    overworld_region = temp_data_dir / "world" / "region"
    nether_dir = temp_data_dir / "world" / "DIM-1"
    world_root = temp_data_dir / "world"
    other_dir = temp_data_dir / "other"

    s1 = await restic_manager.backup([world_root])
    s2 = await restic_manager.backup([overworld_region])
    s3 = await restic_manager.backup([other_dir])
    s4 = await restic_manager.backup([nether_dir, overworld_region])

    overworld_mca = overworld_region / "r.0.0.mca"
    nether_mca = nether_dir / "region" / "r.0.0.mca"
    other_file = other_dir / "file.txt"

    only_overworld = await restic_manager.find_snapshots_covering([overworld_mca])
    only_overworld_ids = {s.id for s in only_overworld}
    assert only_overworld_ids == {s1.id, s2.id, s4.id}

    overworld_and_nether = await restic_manager.find_snapshots_covering(
        [overworld_mca, nether_mca]
    )
    overworld_and_nether_ids = {s.id for s in overworld_and_nether}
    assert overworld_and_nether_ids == {s1.id, s4.id}

    only_other = await restic_manager.find_snapshots_covering([other_file])
    only_other_ids = {s.id for s in only_other}
    assert only_other_ids == {s3.id}


@pytest.mark.asyncio
async def test_find_snapshots_covering_results_newest_first(
    restic_manager, temp_data_dir
):
    overworld_region = temp_data_dir / "world" / "region"

    first = await restic_manager.backup([overworld_region])
    second = await restic_manager.backup([overworld_region])

    snapshots = await restic_manager.find_snapshots_covering(
        [overworld_region / "r.0.0.mca"]
    )
    assert len(snapshots) >= 2
    times = [s.time for s in snapshots]
    assert times == sorted(times, reverse=True)
    # Latest backup has the most recent timestamp
    assert snapshots[0].id in {first.id, second.id}


@pytest.mark.asyncio
async def test_find_snapshots_covering_rejects_empty_paths(restic_manager):
    with pytest.raises(ValueError):
        await restic_manager.find_snapshots_covering([])


@pytest.mark.asyncio
async def test_find_snapshots_covering_rejects_relative_paths(restic_manager):
    with pytest.raises(ValueError):
        await restic_manager.find_snapshots_covering([Path("relative/path")])
