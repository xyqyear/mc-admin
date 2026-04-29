"""System resource metrics. Sync stdlib calls (psutil + shutil) are off-loaded
to a worker thread via ``asyncio.to_thread`` so they don't block the event loop.
"""

import asyncio
import dataclasses
import shutil

import psutil


@dataclasses.dataclass
class SpaceInfo:
    total: float
    used: float


@dataclasses.dataclass
class CPULoad:
    one_minute: float
    five_minutes: float
    fifteen_minutes: float


async def get_cpu_percent() -> float:
    """Get CPU usage percentage (1-second sampling window)."""
    return await asyncio.to_thread(psutil.cpu_percent, 1)


async def get_cpu_load() -> CPULoad:
    """Get CPU load averages for 1, 5, and 15 minutes."""
    return await asyncio.to_thread(_cpu_load_sync)


def _cpu_load_sync() -> CPULoad:
    return CPULoad(*psutil.getloadavg())


async def get_memory_info() -> SpaceInfo:
    """Get memory usage information in bytes."""
    return await asyncio.to_thread(_memory_info_sync)


def _memory_info_sync() -> SpaceInfo:
    mem = psutil.virtual_memory()
    return SpaceInfo(total=mem.total, used=mem.used)


async def get_disk_info(path) -> SpaceInfo:
    """Get disk space information for specified path in bytes."""
    return await asyncio.to_thread(_disk_info_sync, path)


def _disk_info_sync(path) -> SpaceInfo:
    disk = shutil.disk_usage(path)
    return SpaceInfo(total=disk.total, used=disk.used)
