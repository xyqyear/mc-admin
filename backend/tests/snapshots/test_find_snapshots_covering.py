"""Integrated tests for SnapshotService.find_snapshots_covering using real restic."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from app.config import settings
from app.snapshots import ResticClient, SnapshotService
from app.utils.exec import exec_command


def check_restic_available() -> bool:
    try:
        result = subprocess.run(
            [str(settings.restic_binary_path), "version"],
            capture_output=True,
            text=True,
            timeout=5,
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


class _NoInstances:
    async def get_all_instances(self):
        return []


@pytest.fixture
async def snapshot_service(temp_repo_dir):
    client = ResticClient(repository_path=str(temp_repo_dir), password=None)
    await exec_command(
        str(client.binary_path), "init", "--insecure-no-password", env=client.env
    )
    return SnapshotService(client, _NoInstances())


@pytest.mark.asyncio
async def test_find_snapshots_covering_filters_by_and_coverage(
    snapshot_service, temp_data_dir
):
    overworld_region = temp_data_dir / "world" / "region"
    nether_dir = temp_data_dir / "world" / "DIM-1"
    world_root = temp_data_dir / "world"
    other_dir = temp_data_dir / "other"

    s1 = await snapshot_service._client.backup([world_root])
    s2 = await snapshot_service._client.backup([overworld_region])
    s3 = await snapshot_service._client.backup([other_dir])
    s4 = await snapshot_service._client.backup([nether_dir, overworld_region])

    overworld_mca = overworld_region / "r.0.0.mca"
    nether_mca = nether_dir / "region" / "r.0.0.mca"
    other_file = other_dir / "file.txt"

    only_overworld = await snapshot_service.find_snapshots_covering([overworld_mca])
    only_overworld_ids = {s.id for s in only_overworld}
    assert only_overworld_ids == {s1.id, s2.id, s4.id}

    overworld_and_nether = await snapshot_service.find_snapshots_covering(
        [overworld_mca, nether_mca]
    )
    overworld_and_nether_ids = {s.id for s in overworld_and_nether}
    assert overworld_and_nether_ids == {s1.id, s4.id}

    only_other = await snapshot_service.find_snapshots_covering([other_file])
    only_other_ids = {s.id for s in only_other}
    assert only_other_ids == {s3.id}


@pytest.mark.asyncio
async def test_find_snapshots_covering_results_newest_first(
    snapshot_service, temp_data_dir
):
    overworld_region = temp_data_dir / "world" / "region"

    first = await snapshot_service._client.backup([overworld_region])
    second = await snapshot_service._client.backup([overworld_region])

    snapshots = await snapshot_service.find_snapshots_covering(
        [overworld_region / "r.0.0.mca"]
    )
    assert len(snapshots) >= 2
    times = [s.time for s in snapshots]
    assert times == sorted(times, reverse=True)
    # Latest backup has the most recent timestamp
    assert snapshots[0].id in {first.id, second.id}


@pytest.mark.asyncio
async def test_find_snapshots_covering_rejects_empty_paths(snapshot_service):
    with pytest.raises(ValueError):
        await snapshot_service.find_snapshots_covering([])


@pytest.mark.asyncio
async def test_find_snapshots_covering_rejects_relative_paths(snapshot_service):
    with pytest.raises(ValueError):
        await snapshot_service.find_snapshots_covering([Path("relative/path")])


@pytest.mark.asyncio
async def test_find_snapshots_covering_is_exclude_aware(
    snapshot_service, temp_data_dir
):
    """A snapshot whose recorded excludes contain the target must not count
    as covering it, even though its recorded paths do."""
    world_root = temp_data_dir / "world"
    nether_dir = world_root / "DIM-1"
    nether_mca = nether_dir / "region" / "r.0.0.mca"
    overworld_mca = world_root / "region" / "r.0.0.mca"

    full = await snapshot_service._client.backup([world_root])
    without_nether = await snapshot_service._client.backup(
        [world_root], excludes=[str(nether_dir)]
    )

    covering_nether = {
        s.id for s in await snapshot_service.find_snapshots_covering([nether_mca])
    }
    assert full.id in covering_nether
    assert without_nether.id not in covering_nether

    # An exclude below the target does not disqualify the directory itself.
    covering_root = {
        s.id for s in await snapshot_service.find_snapshots_covering([world_root])
    }
    assert full.id in covering_root
    assert without_nether.id in covering_root

    # Untouched by the exclude → both cover.
    covering_overworld = {
        s.id
        for s in await snapshot_service.find_snapshots_covering([overworld_mca])
    }
    assert full.id in covering_overworld
    assert without_nether.id in covering_overworld


@pytest.mark.asyncio
async def test_list_snapshots_path_filter_is_exclude_aware(
    snapshot_service, temp_data_dir
):
    world_root = temp_data_dir / "world"
    nether_dir = world_root / "DIM-1"

    full = await snapshot_service._client.backup([world_root])
    without_nether = await snapshot_service._client.backup(
        [world_root], excludes=[str(nether_dir)]
    )

    filtered = {
        s.id for s in await snapshot_service.list_snapshots(path_filter=nether_dir)
    }
    assert full.id in filtered
    assert without_nether.id not in filtered
