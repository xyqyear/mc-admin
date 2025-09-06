import asyncio

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager, MCServerStatus
from ...minecraft.compose import MCComposeFile
from ...minecraft.docker.compose_file import ComposeFile
from ...models import UserPublic
from .utils.server_list import ServerListItem, get_server_list_item

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


class ServerCpuPercent(BaseModel):
    cpuPercentage: float


class ServerMemory(BaseModel):
    memoryUsageBytes: int


class ServerPlayers(BaseModel):
    onlinePlayers: list[str]


class ServerIOStats(BaseModel):
    # Disk I/O statistics
    diskReadBytes: int
    diskWriteBytes: int
    # Network I/O statistics
    networkReceiveBytes: int
    networkSendBytes: int


class ServerDiskUsage(BaseModel):
    # Disk usage and space information
    diskUsageBytes: int
    diskTotalBytes: int
    diskAvailableBytes: int


class ServerOperation(BaseModel):
    action: str  # start, stop, restart, up, down


class ComposeConfig(BaseModel):
    yaml_content: str


class CreateServerRequest(BaseModel):
    yaml_content: str


# Helper functions for port conflict checking
def extract_ports_from_yaml(yaml_content: str) -> tuple[int, int]:
    """Extract game port and RCON port from YAML content.
    
    Args:
        yaml_content: Docker Compose YAML content
        
    Returns:
        tuple[int, int]: (game_port, rcon_port)
        
    Raises:
        ValueError: If YAML is invalid or doesn't contain required ports
    """
    try:
        # Parse YAML and create compose objects
        compose_dict = yaml.safe_load(yaml_content)
        compose_file = ComposeFile.from_dict(compose_dict)
        mc_compose = MCComposeFile(compose_file)
        
        # Extract ports using existing methods
        game_port = mc_compose.get_game_port()
        rcon_port = mc_compose.get_rcon_port()
        
        return game_port, rcon_port
    except Exception as e:
        raise ValueError(f"Failed to extract ports from YAML: {str(e)}")


async def check_port_conflicts(game_port: int, rcon_port: int) -> list[str]:
    """Check for port conflicts with existing servers.
    
    Args:
        game_port: Game port to check
        rcon_port: RCON port to check
        
    Returns:
        list[str]: List of conflict messages, empty if no conflicts
    """
    conflicts = []
    
    try:
        # Get all existing instances
        instances = await mc_manager.get_all_instances()
        
        for instance in instances:
            try:
                # Get compose file path to check if server exists
                compose_file_path = await instance.get_compose_file_path()
                if compose_file_path is None:
                    # Server doesn't have compose file yet, skip
                    continue
                
                # Parse compose file directly to get port information
                compose_content = await instance.get_compose_file()
                existing_game_port, existing_rcon_port = extract_ports_from_yaml(compose_content)
                
                # Check game port conflict
                if existing_game_port == game_port:
                    conflicts.append(
                        f"Game port {game_port} is already used by server '{instance.get_name()}'"
                    )
                
                # Check RCON port conflict
                if existing_rcon_port == rcon_port:
                    conflicts.append(
                        f"RCON port {rcon_port} is already used by server '{instance.get_name()}'"
                    )
                    
            except Exception:
                # If we can't parse this server's ports, skip it
                continue
                
    except Exception as e:
        # If we can't get instances, that's a more serious error
        raise HTTPException(status_code=500, detail=f"Failed to check port conflicts: {str(e)}")
    
    return conflicts


@router.get("/", response_model=list[ServerListItem])
async def get_servers(_: UserPublic = Depends(get_current_user)):
    """Get list of all servers with basic info only (no status or runtime data)"""
    try:
        # Get all server instances
        instances = await mc_manager.get_all_instances()

        if not instances:
            return []

        # Gather all server data concurrently
        server_data_tasks = [get_server_list_item(instance) for instance in instances]

        servers = await asyncio.gather(*server_data_tasks, return_exceptions=True)

        # Filter out any exceptions and return valid servers
        valid_servers = [
            server for server in servers if not isinstance(server, Exception)
        ]

        return valid_servers

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get servers: {str(e)}")


@router.get("/{server_id}", response_model=ServerInfo)
async def get_server(server_id: str, _: UserPublic = Depends(get_current_user)):
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
            serverType=server_info.server_type,
            gameVersion=server_info.game_version,
            gamePort=server_info.game_port,
            maxMemoryBytes=server_info.max_memory_bytes or 0,
            rconPort=server_info.rcon_port,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server info: {str(e)}"
        )


@router.get("/{server_id}/status", response_model=ServerStatus)
async def get_server_status(server_id: str, _: UserPublic = Depends(get_current_user)):
    """Get current status of a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)
        status = await instance.get_status()

        return ServerStatus(status=status)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server status: {str(e)}"
        )


@router.get("/{server_id}/cpu_percent", response_model=ServerCpuPercent)
async def get_server_cpu_percent(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    """Get CPU percentage for a specific server (available when running/starting/healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where CPU monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' CPU monitoring not available (status: {status})",
            )

        # Get CPU percentage
        cpu_percentage = await instance.get_cpu_percentage()

        return ServerCpuPercent(
            cpuPercentage=cpu_percentage,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server CPU percentage: {str(e)}"
        )


@router.get("/{server_id}/memory", response_model=ServerMemory)
async def get_server_memory(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    """Get memory usage for a specific server (available when running/starting/healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where memory monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' memory monitoring not available (status: {status})",
            )

        # Get memory usage
        memory_stats = await instance.get_memory_usage()

        # Calculate actual memory usage from memory stats (anon + file is commonly used memory)
        memory_usage_bytes = memory_stats.anon + memory_stats.file

        return ServerMemory(
            memoryUsageBytes=memory_usage_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server memory usage: {str(e)}"
        )


@router.get("/{server_id}/players", response_model=ServerPlayers)
async def get_server_players(server_id: str, _: UserPublic = Depends(get_current_user)):
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
async def get_server_iostats(server_id: str, _: UserPublic = Depends(get_current_user)):
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

        # Get I/O statistics concurrently (disk I/O and network I/O only)
        disk_io_task = instance.get_disk_io()
        network_io_task = instance.get_network_io()

        disk_io, network_io = await asyncio.gather(disk_io_task, network_io_task)

        return ServerIOStats(
            diskReadBytes=disk_io.total_read_bytes,
            diskWriteBytes=disk_io.total_write_bytes,
            networkReceiveBytes=network_io.total_rx_bytes,
            networkSendBytes=network_io.total_tx_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server I/O stats: {str(e)}"
        )


@router.get("/{server_id}/disk-usage", response_model=ServerDiskUsage)
async def get_server_disk_usage(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    """Get disk usage information for a specific server (always available regardless of server status)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get disk space information - this is always available regardless of server status
        disk_space = await instance.get_disk_space_info()

        return ServerDiskUsage(
            diskUsageBytes=disk_space.used_bytes,
            diskTotalBytes=disk_space.total_bytes,
            diskAvailableBytes=disk_space.available_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server disk usage: {str(e)}"
        )


@router.get("/{server_id}/compose")
async def get_server_compose(server_id: str, _: UserPublic = Depends(get_current_user)):
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
    server_id: str,
    compose_config: ComposeConfig,
    _: UserPublic = Depends(get_current_user),
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
    server_id: str,
    operation: ServerOperation,
    _: UserPublic = Depends(get_current_user),
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


@router.post("/{server_id}")
async def create_server(
    server_id: str,
    create_request: CreateServerRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a new Minecraft server with the provided Docker Compose configuration"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server already exists
        if await instance.exists():
            raise HTTPException(
                status_code=409, detail=f"Server '{server_id}' already exists"
            )

        # Extract ports from YAML to check for conflicts
        try:
            game_port, rcon_port = extract_ports_from_yaml(create_request.yaml_content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Check for port conflicts with existing servers
        port_conflicts = await check_port_conflicts(game_port, rcon_port)
        if port_conflicts:
            conflict_messages = "; ".join(port_conflicts)
            raise HTTPException(
                status_code=409, 
                detail=f"Port conflicts detected: {conflict_messages}"
            )

        # Create the server using the MCInstance.create method
        await instance.create(create_request.yaml_content)

        return {
            "message": f"Server '{server_id}' created successfully",
            "game_port": game_port,
            "rcon_port": rcon_port
        }

    except HTTPException:
        raise
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create server: {str(e)}")
