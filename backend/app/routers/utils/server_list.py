import asyncio
from typing import Optional

from pydantic import BaseModel

from ...minecraft import MCInstance, MCServerStatus


class ServerListItem(BaseModel):
    """Server list item model with comprehensive server information"""
    id: str
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    status: MCServerStatus
    onlinePlayers: list[str]
    maxMemoryBytes: int
    rconPort: int
    cpuPercentage: Optional[float] = None
    memoryUsageBytes: Optional[int] = None
    diskUsageBytes: Optional[int] = None
    diskTotalBytes: Optional[int] = None
    diskAvailableBytes: Optional[int] = None


async def get_server_list_item(instance: MCInstance) -> ServerListItem:
    """Helper to get server list item data for a single instance"""
    try:
        server_id = instance.get_name()

        # Get basic info and status concurrently
        info_task = instance.get_server_info()
        status_task = instance.get_status()

        server_info, status = await asyncio.gather(info_task, status_task)

        # Initialize with basic data
        list_item = ServerListItem(
            id=server_id,
            name=server_info.name,
            serverType=server_info.server_type or "vanilla",
            gameVersion=server_info.game_version or "latest",
            gamePort=server_info.game_port or 25565,
            status=status,
            onlinePlayers=[],
            maxMemoryBytes=server_info.max_memory_bytes or 2147483648,
            rconPort=server_info.rcon_port
            or 25575,  # Use real RCON port from compose file
        )

        # Get resource data if server is in a state where resource monitoring is available
        if status in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            try:
                cpu_task = instance.get_cpu_percentage()
                memory_task = instance.get_memory_usage()

                cpu_percentage, memory_stats = await asyncio.gather(
                    cpu_task, memory_task, return_exceptions=True
                )

                # Update resource data if successful
                if not isinstance(cpu_percentage, BaseException):
                    list_item.cpuPercentage = cpu_percentage
                if not isinstance(memory_stats, BaseException):
                    list_item.memoryUsageBytes = memory_stats.anon + memory_stats.file

            except Exception:
                # Resource data is optional, continue without it
                pass

        # Get disk space information for any server that exists (doesn't require running state)
        try:
            disk_space = await instance.get_disk_space_info()
            list_item.diskUsageBytes = disk_space.used_bytes
            list_item.diskTotalBytes = disk_space.total_bytes
            list_item.diskAvailableBytes = disk_space.available_bytes
        except Exception:
            # Disk space information is optional, continue without it
            pass

        # Get player data only if server is healthy
        if status == MCServerStatus.HEALTHY:
            try:
                players = await instance.list_players()
                list_item.onlinePlayers = players
            except Exception:
                # Player data is optional, continue without it
                pass

        return list_item

    except Exception as e:
        # Log error but don't fail the entire request
        print(f"Error getting server list item for {instance.get_name()}: {e}")
        # Return minimal data
        return ServerListItem(
            id=instance.get_name(),
            name=instance.get_name(),
            serverType="unknown",
            gameVersion="unknown",
            gamePort=25565,
            status=MCServerStatus.REMOVED,
            onlinePlayers=[],
            maxMemoryBytes=2147483648,
            rconPort=25575,  # Default RCON port
        )