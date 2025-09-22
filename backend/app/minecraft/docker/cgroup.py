"""
Docker cgroup monitoring module for memory and I/O statistics.

This module provides data classes and utilities to read and parse cgroup v2 statistics
for Docker containers, including memory usage and block I/O statistics.
"""

from typing import Dict, List

import aiofiles
from pydantic import BaseModel

from ...config import settings


class MemoryStats(BaseModel):
    """Memory statistics from cgroup v2 memory.stat file.

    All values are in bytes unless otherwise specified.
    """

    anon: int = 0
    file: int = 0
    kernel: int = 0
    kernel_stack: int = 0
    pagetables: int = 0
    sec_pagetables: int = 0
    percpu: int = 0
    sock: int = 0
    vmalloc: int = 0
    shmem: int = 0
    zswap: int = 0
    zswapped: int = 0
    file_mapped: int = 0
    file_dirty: int = 0
    file_writeback: int = 0
    swapcached: int = 0
    anon_thp: int = 0
    file_thp: int = 0
    shmem_thp: int = 0
    inactive_anon: int = 0
    active_anon: int = 0
    inactive_file: int = 0
    active_file: int = 0
    unevictable: int = 0
    slab_reclaimable: int = 0

    @classmethod
    def from_memory_stat_content(cls, content: str) -> "MemoryStats":
        """Parse memory.stat file content into MemoryStats object."""
        stats: Dict[str, int] = {}
        for line in content.strip().split("\n"):
            if line:
                parts = line.split()
                if len(parts) == 2:
                    key, value = parts
                    stats[key] = int(value)
        return cls(**stats)

    @property
    def total_memory(self) -> int:
        """Total memory usage (anon + file)."""
        return self.anon + self.file

    @property
    def active_memory(self) -> int:
        """Active memory (active_anon + active_file)."""
        return self.active_anon + self.active_file

    @property
    def inactive_memory(self) -> int:
        """Inactive memory (inactive_anon + inactive_file)."""
        return self.inactive_anon + self.inactive_file


class BlockIODevice(BaseModel):
    """Block I/O statistics for a single device."""

    major: int
    minor: int
    rbytes: int = 0  # Read bytes
    wbytes: int = 0  # Write bytes
    rios: int = 0  # Read I/O operations
    wios: int = 0  # Write I/O operations
    dbytes: int = 0  # Discard bytes
    dios: int = 0  # Discard I/O operations

    @property
    def device_id(self) -> str:
        """Device identifier as major:minor."""
        return f"{self.major}:{self.minor}"

    @property
    def total_bytes(self) -> int:
        """Total bytes (read + write + discard)."""
        return self.rbytes + self.wbytes + self.dbytes

    @property
    def total_operations(self) -> int:
        """Total I/O operations (read + write + discard)."""
        return self.rios + self.wios + self.dios


class BlockIOStats(BaseModel):
    """Block I/O statistics from cgroup v2 io.stat file."""

    devices: List[BlockIODevice] = []

    @classmethod
    def from_io_stat_content(cls, content: str) -> "BlockIOStats":
        """Parse io.stat file content into BlockIOStats object."""
        devices: List[BlockIODevice] = []
        for line in content.strip().split("\n"):
            if line:
                parts = line.split()
                if len(parts) >= 1:
                    device_id = parts[0]
                    major, minor = map(int, device_id.split(":"))

                    # Parse key=value pairs
                    stats: Dict[str, int] = {"major": major, "minor": minor}
                    for part in parts[1:]:
                        if "=" in part:
                            key, value = part.split("=", 1)
                            stats[key] = int(value)

                    devices.append(BlockIODevice(**stats))

        return cls(devices=devices)

    def get_device_by_id(self, device_id: str) -> BlockIODevice | None:
        """Get device statistics by device ID (major:minor)."""
        for device in self.devices:
            if device.device_id == device_id:
                return device
        return None

    @property
    def total_read_bytes(self) -> int:
        """Total read bytes across all devices."""
        return sum(device.rbytes for device in self.devices)

    @property
    def total_write_bytes(self) -> int:
        """Total write bytes across all devices."""
        return sum(device.wbytes for device in self.devices)

    @property
    def total_bytes(self) -> int:
        """Total bytes across all devices."""
        return sum(device.total_bytes for device in self.devices)

    @property
    def total_operations(self) -> int:
        """Total I/O operations across all devices."""
        return sum(device.total_operations for device in self.devices)


class CGroupStats(BaseModel):
    """Combined cgroup statistics for a Docker container."""

    container_id: str
    memory: MemoryStats | None = None
    block_io: BlockIOStats | None = None


async def read_memory_stats(container_id: str) -> MemoryStats:
    """Read memory statistics for a Docker container."""
    memory_stat_path = (
        settings.cgroup_path / f"system.slice/docker-{container_id}.scope/memory.stat"
    )

    try:
        async with aiofiles.open(memory_stat_path, "r") as f:
            content = await f.read()
        return MemoryStats.from_memory_stat_content(content)
    except FileNotFoundError:
        raise FileNotFoundError(f"Memory stats not found for container {container_id}")
    except Exception as e:
        raise RuntimeError(
            f"Failed to read memory stats for container {container_id}: {e}"
        )


async def read_block_io_stats(container_id: str) -> BlockIOStats:
    """Read block I/O statistics for a Docker container."""
    io_stat_path = (
        settings.cgroup_path / f"system.slice/docker-{container_id}.scope/io.stat"
    )

    try:
        async with aiofiles.open(io_stat_path, "r") as f:
            content = await f.read()
        return BlockIOStats.from_io_stat_content(content)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Block I/O stats not found for container {container_id}"
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to read block I/O stats for container {container_id}: {e}"
        )


async def read_cgroup_stats(container_id: str) -> CGroupStats:
    """Read all available cgroup statistics for a Docker container."""
    stats = CGroupStats(container_id=container_id)

    try:
        stats.memory = await read_memory_stats(container_id)
    except Exception:
        # Memory stats are optional if not available
        pass

    try:
        stats.block_io = await read_block_io_stats(container_id)
    except Exception:
        # Block I/O stats are optional if not available
        pass

    return stats
