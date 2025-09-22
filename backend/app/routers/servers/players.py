from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager, MCServerStatus
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["server-players"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


class ServerPlayers(BaseModel):
    onlinePlayers: list[str]


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
