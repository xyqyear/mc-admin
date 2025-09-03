import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..dependencies import get_current_user
from ..minecraft import DockerMCManager, MCInstance, MCServerStatus

router = APIRouter(
    prefix="/servers",
    tags=["servers"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


# Pydantic models for API responses
class ServerInfo(BaseModel):
    id: str
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    maxMemoryBytes: int
    rconPort: int


class ServerStatus(BaseModel):
    status: MCServerStatus


class ServerResources(BaseModel):
    cpuPercentage: float
    memoryUsageBytes: int


class ServerPlayers(BaseModel):
    onlinePlayers: list[str]


class ServerListItem(BaseModel):
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


class ServerIOStats(BaseModel):
    # Disk I/O statistics
    diskReadBytes: int
    diskWriteBytes: int
    # Network I/O statistics
    networkReceiveBytes: int
    networkSendBytes: int
    # Disk usage and space information
    diskUsageBytes: int
    diskTotalBytes: int
    diskAvailableBytes: int


class ServerOperation(BaseModel):
    action: str  # start, stop, restart, up, down


class ComposeConfig(BaseModel):
    yaml_content: str


# Helper functions


# API Endpoints


@router.get("/", response_model=list[ServerListItem])
async def get_servers(_: str = Depends(get_current_user)):
    """Get list of all servers with their basic info and current status"""
    try:
        # Get all server instances
        instances = await mc_manager.get_all_instances()

        if not instances:
            return []

        # Gather all server data concurrently
        server_data_tasks = [_get_server_list_item(instance) for instance in instances]

        servers = await asyncio.gather(*server_data_tasks, return_exceptions=True)

        # Filter out any exceptions and return valid servers
        valid_servers = [
            server for server in servers if not isinstance(server, Exception)
        ]

        return valid_servers

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get servers: {str(e)}")


@router.get("/{server_id}", response_model=ServerInfo)
async def get_server(server_id: str, _: str = Depends(get_current_user)):
    """Get detailed information about a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get server info
        server_info = await instance.get_server_info()

        return ServerInfo(
            id=server_id,
            name=server_info.name,
            serverType=server_info.server_type or "vanilla",
            gameVersion=server_info.game_version or "latest",
            gamePort=server_info.game_port or 25565,
            maxMemoryBytes=server_info.max_memory_bytes or 2147483648,  # 2GB default
            rconPort=server_info.rcon_port
            or 25575,  # Use real RCON port from compose file
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server info: {str(e)}"
        )


@router.get("/{server_id}/status", response_model=ServerStatus)
async def get_server_status(server_id: str, _: str = Depends(get_current_user)):
    """Get current status of a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)
        status = await instance.get_status()

        return ServerStatus(status=status)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server status: {str(e)}"
        )


@router.get("/{server_id}/resources", response_model=ServerResources)
async def get_server_resources(server_id: str, _: str = Depends(get_current_user)):
    """Get system resource information for a specific server (available when running/starting/healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where resource monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' resources not available (status: {status})",
            )

        # Get resource data concurrently
        cpu_task = instance.get_cpu_percentage()
        memory_task = instance.get_memory_usage()

        cpu_percentage, memory_stats = await asyncio.gather(cpu_task, memory_task)

        # Calculate actual memory usage from memory stats (anon + file is commonly used memory)
        memory_usage_bytes = memory_stats.anon + memory_stats.file

        return ServerResources(
            cpuPercentage=cpu_percentage,
            memoryUsageBytes=memory_usage_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server resources: {str(e)}"
        )


@router.get("/{server_id}/players", response_model=ServerPlayers)
async def get_server_players(server_id: str, _: str = Depends(get_current_user)):
    """Get online players for a specific server (only available when healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is healthy (required for player list)
        status = await instance.get_status()
        if status != MCServerStatus.HEALTHY:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' players not available - server must be healthy (current status: {status})",
            )

        # Get player list
        players = await instance.list_players()

        return ServerPlayers(
            onlinePlayers=players,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server players: {str(e)}"
        )


@router.get("/{server_id}/iostats", response_model=ServerIOStats)
async def get_server_iostats(server_id: str, _: str = Depends(get_current_user)):
    """Get comprehensive I/O statistics for a specific server (disk I/O, network I/O, disk usage)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where I/O monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' I/O stats not available (status: {status})",
            )

        # Get I/O statistics concurrently
        disk_io_task = instance.get_disk_io()
        network_io_task = instance.get_network_io()
        disk_space_task = instance.get_disk_space_info()

        disk_io, network_io, disk_space = await asyncio.gather(
            disk_io_task, network_io_task, disk_space_task
        )

        return ServerIOStats(
            diskReadBytes=disk_io.total_read_bytes,
            diskWriteBytes=disk_io.total_write_bytes,
            networkReceiveBytes=network_io.total_rx_bytes,
            networkSendBytes=network_io.total_tx_bytes,
            diskUsageBytes=disk_space.used_bytes,
            diskTotalBytes=disk_space.total_bytes,
            diskAvailableBytes=disk_space.available_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server I/O stats: {str(e)}"
        )


@router.get("/{server_id}/compose")
async def get_server_compose(server_id: str, _: str = Depends(get_current_user)):
    """Get the Docker Compose configuration for a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get compose file content
        compose_content = await instance.get_compose_file()

        return {"yaml_content": compose_content}

    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Compose file not found for server '{server_id}'"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get compose configuration: {str(e)}"
        )


@router.post("/{server_id}/compose")
async def update_server_compose(
    server_id: str, compose_config: ComposeConfig, _: str = Depends(get_current_user)
):
    """Update the Docker Compose configuration for a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get current server status
        status = await instance.get_status()

        # If server is running, stop it first
        server_was_running = False
        if status in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            server_was_running = True
            await instance.down()

        try:
            # Update the compose file
            await instance.update_compose_file(compose_config.yaml_content)

            # If server was running, start it again
            if server_was_running:
                await instance.up()

            return {
                "message": f"Server '{server_id}' compose configuration updated successfully"
            }

        except Exception as e:
            # If something goes wrong and server was running, try to start it again with the original config
            if server_was_running:
                try:
                    await instance.up()
                except Exception:
                    pass  # Best effort to restart
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update compose configuration: {str(e)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update compose configuration: {str(e)}"
        )


@router.post("/{server_id}/operations")
async def server_operation(
    server_id: str, operation: ServerOperation, _: str = Depends(get_current_user)
):
    """Perform operations on a server (start, stop, restart, up, down)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        action = operation.action.lower()

        if action == "start":
            await instance.start()
        elif action == "stop":
            await instance.stop()
        elif action == "restart":
            await instance.restart()
        elif action == "up":
            await instance.up()
        elif action == "down":
            await instance.down()
        elif action == "remove":
            await instance.remove()
        else:
            raise HTTPException(status_code=400, detail=f"Invalid operation: {action}")

        return {"message": f"Server '{server_id}' {action} operation completed"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Operation failed: {str(e)}")




# Helper function
async def _get_server_list_item(instance: MCInstance) -> ServerListItem:
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
