"""
Docker network monitoring module for network I/O statistics.

This module provides data classes and utilities to read and parse network
statistics from /proc/{PID}/net/dev for Docker containers.
"""

from typing import List

import aiofiles
from pydantic import BaseModel


class NetworkInterface(BaseModel):
    """Network interface statistics from /proc/net/dev."""

    name: str
    # Receive statistics
    rx_bytes: int = 0
    rx_packets: int = 0
    rx_errs: int = 0
    rx_drop: int = 0
    rx_fifo: int = 0
    rx_frame: int = 0
    rx_compressed: int = 0
    rx_multicast: int = 0
    # Transmit statistics
    tx_bytes: int = 0
    tx_packets: int = 0
    tx_errs: int = 0
    tx_drop: int = 0
    tx_fifo: int = 0
    tx_colls: int = 0
    tx_carrier: int = 0
    tx_compressed: int = 0

    @property
    def total_bytes(self) -> int:
        """Total bytes (received + transmitted)."""
        return self.rx_bytes + self.tx_bytes

    @property
    def total_packets(self) -> int:
        """Total packets (received + transmitted)."""
        return self.rx_packets + self.tx_packets

    @property
    def total_errors(self) -> int:
        """Total errors (received + transmitted)."""
        return self.rx_errs + self.tx_errs

    @property
    def total_drops(self) -> int:
        """Total drops (received + transmitted)."""
        return self.rx_drop + self.tx_drop


class NetworkStats(BaseModel):
    """Network statistics for a process/container."""

    pid: int
    interfaces: List[NetworkInterface] = []

    @classmethod
    def from_net_dev_content(cls, pid: int, content: str) -> "NetworkStats":
        """Parse /proc/{pid}/net/dev file content into NetworkStats object."""
        interfaces: List[NetworkInterface] = []
        lines = content.strip().split("\n")

        # Skip the first two header lines
        if len(lines) < 3:
            return cls(pid=pid, interfaces=[])

        for line in lines[2:]:  # Skip header lines
            line = line.strip()
            if not line:
                continue

            # Split interface name from the rest
            if ":" not in line:
                continue

            name_part, stats_part = line.split(":", 1)
            interface_name = name_part.strip()

            # Parse the statistics
            stats = stats_part.split()
            if len(stats) >= 16:
                try:
                    interface = NetworkInterface(
                        name=interface_name,
                        rx_bytes=int(stats[0]),
                        rx_packets=int(stats[1]),
                        rx_errs=int(stats[2]),
                        rx_drop=int(stats[3]),
                        rx_fifo=int(stats[4]),
                        rx_frame=int(stats[5]),
                        rx_compressed=int(stats[6]),
                        rx_multicast=int(stats[7]),
                        tx_bytes=int(stats[8]),
                        tx_packets=int(stats[9]),
                        tx_errs=int(stats[10]),
                        tx_drop=int(stats[11]),
                        tx_fifo=int(stats[12]),
                        tx_colls=int(stats[13]),
                        tx_carrier=int(stats[14]),
                        tx_compressed=int(stats[15]),
                    )
                    interfaces.append(interface)
                except (ValueError, IndexError):
                    # Skip malformed lines
                    continue

        return cls(pid=pid, interfaces=interfaces)

    def get_interface_by_name(self, name: str) -> NetworkInterface | None:
        """Get interface statistics by interface name."""
        for interface in self.interfaces:
            if interface.name == name:
                return interface
        return None

    @property
    def total_rx_bytes(self) -> int:
        """Total received bytes across all interfaces."""
        return sum(interface.rx_bytes for interface in self.interfaces)

    @property
    def total_tx_bytes(self) -> int:
        """Total transmitted bytes across all interfaces."""
        return sum(interface.tx_bytes for interface in self.interfaces)

    @property
    def total_bytes(self) -> int:
        """Total bytes across all interfaces."""
        return sum(interface.total_bytes for interface in self.interfaces)

    @property
    def total_rx_packets(self) -> int:
        """Total received packets across all interfaces."""
        return sum(interface.rx_packets for interface in self.interfaces)

    @property
    def total_tx_packets(self) -> int:
        """Total transmitted packets across all interfaces."""
        return sum(interface.tx_packets for interface in self.interfaces)

    @property
    def total_packets(self) -> int:
        """Total packets across all interfaces."""
        return sum(interface.total_packets for interface in self.interfaces)

    @property
    def total_errors(self) -> int:
        """Total errors across all interfaces."""
        return sum(interface.total_errors for interface in self.interfaces)

    @property
    def total_drops(self) -> int:
        """Total drops across all interfaces."""
        return sum(interface.total_drops for interface in self.interfaces)

    @property
    def non_loopback_interfaces(self) -> List[NetworkInterface]:
        """Get all non-loopback interfaces."""
        return [interface for interface in self.interfaces if interface.name != "lo"]

    @property
    def external_traffic_bytes(self) -> int:
        """Total bytes for non-loopback interfaces only."""
        return sum(interface.total_bytes for interface in self.non_loopback_interfaces)


async def read_network_stats(pid: int) -> NetworkStats:
    """Read network statistics for a process by PID."""
    net_dev_path = f"/proc/{pid}/net/dev"

    try:
        async with aiofiles.open(net_dev_path, "r") as f:
            content = await f.read()
        return NetworkStats.from_net_dev_content(pid, content)
    except FileNotFoundError:
        raise FileNotFoundError(f"Network stats not found for PID {pid}")
    except Exception as e:
        raise RuntimeError(f"Failed to read network stats for PID {pid}: {e}")


async def read_container_network_stats(container_pid: int) -> NetworkStats:
    """Read network statistics for a Docker container by its main process PID."""
    return await read_network_stats(container_pid)
