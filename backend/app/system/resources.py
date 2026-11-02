"""System resource metrics. Sync psutil/shutil calls run via ``asyncio.to_thread``."""

import asyncio
import dataclasses
import shutil
import sys
from pathlib import Path

import psutil

from ..errors import PublicOperationError
from ..operations.finalization import finalize

_BTRFS_SYSFS = Path("/sys/fs/btrfs")


@dataclasses.dataclass
class SpaceInfo:
    total: int
    used: int
    available: int = 0


async def get_disk_info(path: str | Path) -> SpaceInfo:
    """Filesystem or limiting Btrfs quota space for ``path`` in bytes."""
    return await finalize(asyncio.to_thread(_disk_info_sync, path))


def _disk_info_sync(path: str | Path) -> SpaceInfo:
    disk = shutil.disk_usage(path)
    space = SpaceInfo(total=disk.total, used=disk.used, available=disk.free)
    if sys.platform != "linux":
        return space

    directory = Path(path).resolve(strict=True)
    mounts = [mount for mount in psutil.disk_partitions(all=True) if directory.is_relative_to(mount.mountpoint)]
    if not mounts:
        raise PublicOperationError("无法识别目录所在的文件系统")
    mount = max(mounts, key=lambda entry: len(Path(entry.mountpoint).parts))
    if mount.fstype != "btrfs":
        return space

    try:
        return _btrfs_quota_space(directory, Path(mount.mountpoint), mount.device, mount.opts, space)
    except (OSError, ValueError) as exc:
        raise PublicOperationError("无法读取 Btrfs 配额，无法确定可用空间") from exc


def _quota_number(path: Path) -> int:
    value = int(path.read_text().strip())
    if value < 0:
        raise ValueError("negative quota value")
    return value


def _btrfs_quota_space(
    directory: Path, mountpoint: Path, device: str, options: str, filesystem: SpaceInfo,
) -> SpaceInfo:
    # Nested subvolumes have separate device IDs even without a separate mount.
    if directory.stat().st_dev != mountpoint.stat().st_dev:
        raise PublicOperationError("无法识别目录对应的 Btrfs 子卷配额")
    subvolume = next((int(option.removeprefix("subvolid=")) for option in options.split(",") if option.startswith("subvolid=")), None)
    if subvolume is None or subvolume < 0:
        raise PublicOperationError("无法识别目录对应的 Btrfs 子卷配额")

    device_name = Path(device).resolve().name
    filesystems = [entry for entry in _BTRFS_SYSFS.iterdir() if (entry / "devices" / device_name).is_symlink()]
    if len(filesystems) != 1:
        raise PublicOperationError("无法识别 Btrfs 文件系统对应的配额统计")
    groups = filesystems[0] / "qgroups"
    if not groups.exists() or _quota_number(groups / "enabled") == 0:
        return filesystem
    if _quota_number(groups / "inconsistent") != 0:
        raise PublicOperationError("Btrfs 配额统计不一致，无法确定可用空间")

    # Sysfs exposes group counters, but not the parent relationships.
    for group in groups.iterdir():
        if group.is_dir() and not group.name.startswith("0_") and _quota_number(group / "limit_flags") & 3:
            raise PublicOperationError("无法确定 Btrfs 层级配额限制下的可用空间")

    group = groups / f"0_{subvolume}"
    flags = _quota_number(group / "limit_flags")
    limits = [
        (_quota_number(group / f"max_{kind}"), _quota_number(group / kind))
        for flag, kind in ((1, "referenced"), (2, "exclusive")) if flags & flag
    ]
    if not limits:
        return filesystem
    reserved = sum(_quota_number(group / name) for name in ("rsv_data", "rsv_meta_pertrans", "rsv_meta_prealloc"))
    total, used = min(limits, key=lambda limit: limit[0] - limit[1])
    available = max(0, min(filesystem.available, total - used - reserved))
    if _quota_number(groups / "inconsistent") != 0:
        raise PublicOperationError("Btrfs 配额统计不一致，无法确定可用空间")
    return SpaceInfo(total=total, used=used, available=available)
