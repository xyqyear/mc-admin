import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager
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
    status: str




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

        return ServerStatus(status=str(status))

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server status: {str(e)}"
        )
