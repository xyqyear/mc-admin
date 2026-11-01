"""System resource metrics. Sync psutil/shutil calls run via ``asyncio.to_thread``."""

import asyncio
import dataclasses
import shutil

from ..operations.finalization import finalize


@dataclasses.dataclass
class SpaceInfo:
    total: int
    used: int
    available: int = 0


async def get_disk_info(path) -> SpaceInfo:
    """Disk space for ``path`` in bytes."""
    return await finalize(asyncio.to_thread(_disk_info_sync, path))


def _disk_info_sync(path) -> SpaceInfo:
    disk = shutil.disk_usage(path)
    return SpaceInfo(total=disk.total, used=disk.used, available=disk.free)
