import dataclasses

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


def get_cpu_percent() -> float:
    """Get CPU usage percentage"""
    return psutil.cpu_percent()


def get_cpu_load() -> CPULoad:
    """Get CPU load averages for 1, 5, and 15 minutes"""
    return CPULoad(*psutil.getloadavg())


def get_memory_info() -> SpaceInfo:
    """Get memory usage information in bytes"""
    mem = psutil.virtual_memory()
    return SpaceInfo(total=mem.total, used=mem.used)


def get_disk_info(path) -> SpaceInfo:
    """Get disk space information for specified path in bytes"""
    disk = psutil.disk_usage(path)
    return SpaceInfo(total=disk.total, used=disk.used)
