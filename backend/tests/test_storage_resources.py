from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.config import ResticSettings
from app.dynamic_config.configs.self_check import SelfCheckConfig
from app.errors import PublicOperationError
from app.main import create_api_app
from app.self_check.checks.base import SelfCheckContext
from app.self_check.checks.storage import check_backup_repository_usage
from app.system import resources
from app.system.resources import SpaceInfo, get_disk_info

GIB = 1024**3


def write_counters(directory: Path, **values: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in values.items():
        (directory / name).write_text(str(value))


@pytest.fixture
def storage(tmp_path, monkeypatch):
    mountpoint = tmp_path / "backup files"
    repository = mountpoint / "restic"
    repository.mkdir(parents=True)
    sysfs = tmp_path / "sysfs"
    filesystem = sysfs / "30b7b1b6-4a15-443b-83ae-b155484910aa"
    devices = filesystem / "devices"
    devices.mkdir(parents=True)
    (devices / "nvme2n1").symlink_to(tmp_path / "block-device")
    groups = filesystem / "qgroups"
    write_counters(groups, enabled=1, inconsistent=0)
    quota = groups / "0_287"
    write_counters(
        quota, limit_flags=1, max_referenced=400 * GIB, referenced=124 * GIB,
        max_exclusive=0, exclusive=120 * GIB,
        rsv_data=0, rsv_meta_pertrans=0, rsv_meta_prealloc=0,
    )
    native = SimpleNamespace(total=1000 * GIB, used=200 * GIB, free=800 * GIB)
    mount = SimpleNamespace(
        device="/dev/nvme2n1", mountpoint=str(mountpoint), fstype="btrfs",
        opts="rw,compress=zstd:1,subvolid=287,subvol=/backups",
    )
    mounts = [SimpleNamespace(device="/dev/root", mountpoint="/", fstype="ext4", opts="rw"), mount]
    monkeypatch.setattr(resources, "_BTRFS_SYSFS", sysfs)
    monkeypatch.setattr(resources.psutil, "disk_partitions", lambda all=False: mounts)
    monkeypatch.setattr(resources.shutil, "disk_usage", lambda path: native)
    return SimpleNamespace(
        repository=repository, mount=mount, groups=groups, quota=quota,
        sysfs=sysfs, native=native,
    )


async def test_btrfs_capacity_uses_the_mounted_subvolumes_real_quota(storage):
    assert await get_disk_info(storage.repository) == SpaceInfo(400 * GIB, 124 * GIB, 276 * GIB)


@pytest.mark.parametrize("filesystem_free,expected_free", [(10, 10), (800, 270)])
async def test_available_space_respects_reservations_and_filesystem_headroom(storage, filesystem_free, expected_free):
    storage.native.free = filesystem_free * GIB
    write_counters(storage.quota, rsv_data=GIB, rsv_meta_pertrans=2 * GIB, rsv_meta_prealloc=3 * GIB)

    assert await get_disk_info(storage.repository) == SpaceInfo(400 * GIB, 124 * GIB, expected_free * GIB)


@pytest.mark.parametrize("limit,used", [(0, 0), (100, 124), (124, 124)])
async def test_exhausted_or_lowered_quota_reports_no_available_space(storage, limit, used):
    write_counters(storage.quota, max_referenced=limit * GIB, referenced=used * GIB)

    assert await get_disk_info(storage.repository) == SpaceInfo(limit * GIB, used * GIB, 0)


async def test_the_tighter_exclusive_limit_controls_capacity(storage):
    write_counters(storage.quota, limit_flags=3, max_exclusive=200 * GIB, exclusive=100 * GIB)

    assert await get_disk_info(storage.repository) == SpaceInfo(200 * GIB, 100 * GIB, 100 * GIB)


@pytest.mark.parametrize("condition", ["ext4", "disabled", "unlimited", "quota-disabled"])
async def test_paths_without_an_applicable_quota_keep_filesystem_statistics(storage, condition):
    if condition == "ext4":
        storage.mount.fstype = "ext4"
    elif condition == "disabled":
        write_counters(storage.groups, enabled=0)
    elif condition == "unlimited":
        write_counters(storage.quota, limit_flags=0)
    else:
        for file in storage.quota.iterdir():
            file.unlink()
        storage.quota.rmdir()
        for file in storage.groups.iterdir():
            file.unlink()
        storage.groups.rmdir()

    assert await get_disk_info(storage.repository) == SpaceInfo(1000 * GIB, 200 * GIB, 800 * GIB)


async def test_a_similar_directory_name_does_not_match_the_btrfs_mount(storage):
    sibling = Path(str(storage.repository.parent) + "-other")
    sibling.mkdir()

    assert await get_disk_info(sibling) == SpaceInfo(1000 * GIB, 200 * GIB, 800 * GIB)


@pytest.mark.parametrize("condition", ["missing", "malformed", "negative", "inconsistent", "hierarchy", "identity", "ambiguous", "subvolume"])
async def test_unknown_quota_is_never_reported_as_whole_disk_capacity(storage, condition):
    if condition == "missing":
        (storage.quota / "referenced").unlink()
    elif condition == "malformed":
        (storage.quota / "referenced").write_text("invalid")
    elif condition == "negative":
        write_counters(storage.quota, referenced=-1)
    elif condition == "inconsistent":
        write_counters(storage.groups, inconsistent=1)
    elif condition == "hierarchy":
        write_counters(storage.groups / "1_42", limit_flags=1)
    elif condition == "identity":
        storage.mount.device = "/dev/another-device"
    elif condition == "ambiguous":
        devices = storage.sysfs / "another-filesystem" / "devices"
        devices.mkdir(parents=True)
        (devices / "nvme2n1").symlink_to("unavailable-device")
    else:
        storage.mount.opts = "rw"

    with pytest.raises(PublicOperationError, match="Btrfs"):
        await get_disk_info(storage.repository)


async def test_permission_failure_does_not_fall_back_to_whole_disk(storage, monkeypatch):
    read_text = Path.read_text

    def denied(path, *args, **kwargs):
        if path == storage.quota / "referenced":
            raise PermissionError("private mount information")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PublicOperationError, match="无法读取 Btrfs 配额"):
        await get_disk_info(storage.repository)


async def test_unmounted_nested_subvolume_is_not_assigned_its_parents_quota(storage, monkeypatch):
    stat = Path.stat

    def nested_device(path, *args, **kwargs):
        result = stat(path, *args, **kwargs)
        if path == storage.repository:
            return SimpleNamespace(st_dev=result.st_dev + 1)
        return result

    monkeypatch.setattr(Path, "stat", nested_device)
    with pytest.raises(PublicOperationError, match="子卷配额"):
        await get_disk_info(storage.repository)


@pytest.fixture
async def storage_api(storage, database, isolated_runtime):
    isolated_runtime.settings.restic = ResticSettings(repository_path=str(storage.repository))
    app = create_api_app(isolated_runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {isolated_runtime.settings.master_token}"
        yield client


async def test_backup_api_uses_effective_quota_and_available_space(storage, storage_api):
    write_counters(storage.quota, rsv_data=GIB)
    response = await storage_api.get("/snapshots/usage")

    assert response.status_code == 200, response.text
    assert response.json() == {"backupTotalGB": 400, "backupUsedGB": 124, "backupAvailableGB": 275}


async def test_backup_api_preserves_native_available_space(storage, storage_api):
    storage.mount.fstype = "ext4"
    storage.native.free = 750 * GIB
    response = await storage_api.get("/snapshots/usage")

    assert response.status_code == 200, response.text
    assert response.json() == {"backupTotalGB": 1000, "backupUsedGB": 200, "backupAvailableGB": 750}


async def test_backup_api_reports_inconsistent_quota_and_recovers(storage, storage_api):
    write_counters(storage.groups, inconsistent=1)
    response = await storage_api.get("/snapshots/usage")

    assert response.status_code == 500
    assert response.json() == {"detail": "Btrfs 配额统计不一致，无法确定可用空间"}

    write_counters(storage.groups, inconsistent=0)
    response = await storage_api.get("/snapshots/usage")
    assert response.status_code == 200, response.text
    assert response.json()["backupAvailableGB"] == 276


async def test_storage_self_check_uses_quota_threshold_and_recovers(
    storage, database, runtime_config, db_session, isolated_runtime,
):
    isolated_runtime.settings.restic = ResticSettings(repository_path=str(storage.repository))
    context = SelfCheckContext(db_session, SelfCheckConfig(backup_repository_usage_percent=80))
    write_counters(storage.quota, referenced=360 * GIB)

    result, = await check_backup_repository_usage(context)
    assert result.status == "warning"
    assert result.evidence["total_bytes"] == 400 * GIB
    assert result.evidence["used_bytes"] == 360 * GIB
    assert result.evidence["usage_percent"] == 90

    write_counters(storage.groups, inconsistent=1)
    result, = await check_backup_repository_usage(context)
    assert result.status == "warning"
    assert result.evidence["error"] == "Btrfs 配额统计不一致，无法确定可用空间"

    write_counters(storage.groups, inconsistent=0)
    write_counters(storage.quota, referenced=124 * GIB)
    result, = await check_backup_repository_usage(context)
    assert result.status == "passed"


@pytest.mark.parametrize("quota_limit,filesystem_free", [(400, 10), (0, 800)])
async def test_storage_self_check_warns_when_filesystem_or_zero_quota_blocks_writes(
    storage, database, runtime_config, db_session, isolated_runtime, quota_limit, filesystem_free,
):
    isolated_runtime.settings.restic = ResticSettings(repository_path=str(storage.repository))
    context = SelfCheckContext(db_session, SelfCheckConfig(backup_repository_usage_percent=80))
    storage.native.free = filesystem_free * GIB
    write_counters(storage.quota, max_referenced=quota_limit * GIB)

    result, = await check_backup_repository_usage(context)
    assert result.status == "warning"
    assert result.evidence["usage_percent"] >= 80
