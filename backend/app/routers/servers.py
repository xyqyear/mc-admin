import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from minecraft_docker_manager_lib import DockerMCManager, MCInstance, MCServerStatus
from pydantic import BaseModel

from ..config import settings
from ..dependencies import get_current_user

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


class ServerRuntime(BaseModel):
    onlinePlayers: list[str]
    cpuPercentage: float
    memoryUsageBytes: int


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


class ServerOperation(BaseModel):
    action: str  # start, stop, restart, up, down


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
        server_data_tasks = [
            _get_server_list_item(instance) 
            for instance in instances
        ]
        
        servers = await asyncio.gather(*server_data_tasks, return_exceptions=True)
        
        # Filter out any exceptions and return valid servers
        valid_servers = [
            server for server in servers 
            if not isinstance(server, Exception)
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
            raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
        
        # Get server info
        server_info = await instance.get_server_info()
        
        return ServerInfo(
            id=server_id,
            name=server_info.name,
            serverType=server_info.server_type or "vanilla",
            gameVersion=server_info.game_version or "latest", 
            gamePort=server_info.game_port or 25565,
            maxMemoryBytes=server_info.max_memory_bytes or 2147483648,  # 2GB default
            rconPort=server_info.rcon_port or 25575,  # Use real RCON port from compose file
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get server info: {str(e)}")


@router.get("/{server_id}/status", response_model=ServerStatus)
async def get_server_status(server_id: str, _: str = Depends(get_current_user)):
    """Get current status of a specific server"""
    try:
        instance = mc_manager.get_instance(server_id)
        status = await instance.get_status()
        
        return ServerStatus(status=status)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get server status: {str(e)}")


@router.get("/{server_id}/runtime", response_model=ServerRuntime)
async def get_server_runtime(server_id: str, _: str = Depends(get_current_user)):
    """Get runtime information for a specific server (only available when running)"""
    try:
        instance = mc_manager.get_instance(server_id)
        
        # Check if server is running (includes RUNNING, STARTING, HEALTHY states)
        status = await instance.get_status()
        if status not in [MCServerStatus.RUNNING, MCServerStatus.STARTING, MCServerStatus.HEALTHY]:
            raise HTTPException(status_code=409, detail=f"Server '{server_id}' is not running (status: {status})")
        
        # Get runtime data concurrently
        players_task = instance.list_players()
        cpu_task = instance.get_cpu_percentage() 
        memory_task = instance.get_memory_usage()
        
        players, cpu_percentage, memory_stats = await asyncio.gather(
            players_task, cpu_task, memory_task
        )
        
        # Calculate actual memory usage from memory stats (anon + file is commonly used memory)
        memory_usage_bytes = memory_stats.anon + memory_stats.file
        
        return ServerRuntime(
            onlinePlayers=players,
            cpuPercentage=cpu_percentage,
            memoryUsageBytes=memory_usage_bytes,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get server runtime: {str(e)}")


@router.post("/{server_id}/operations")
async def server_operation(
    server_id: str, 
    operation: ServerOperation,
    _: str = Depends(get_current_user)
):
    """Perform operations on a server (start, stop, restart, up, down)"""
    try:
        instance = mc_manager.get_instance(server_id)
        
        # Check if server exists
        if not await instance.exists():
            raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
        
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
            rconPort=server_info.rcon_port or 25575,  # Use real RCON port from compose file
        )
        
        # If server is running, get runtime data
        if status in [MCServerStatus.RUNNING, MCServerStatus.HEALTHY]:
            try:
                players_task = instance.list_players()
                cpu_task = instance.get_cpu_percentage()
                memory_task = instance.get_memory_usage()
                
                results = await asyncio.gather(
                    players_task, cpu_task, memory_task, return_exceptions=True
                )
                players, cpu_percentage, memory_stats = results
                
                # Update runtime data if successful
                if not isinstance(players, BaseException):
                    list_item.onlinePlayers = players
                if not isinstance(cpu_percentage, BaseException):
                    list_item.cpuPercentage = cpu_percentage
                if not isinstance(memory_stats, BaseException):
                    list_item.memoryUsageBytes = memory_stats.anon + memory_stats.file
                    
            except Exception:
                # Runtime data is optional, continue without it
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