from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...dependencies import get_current_user
from ...minecraft import MCServerStatus, docker_mc_manager
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["rcon"],
)


class RconCommand(BaseModel):
    command: str


@router.post("/{server_id}/rcon")
async def send_rcon_command(
    server_id: str, rcon_command: RconCommand, _: UserPublic = Depends(get_current_user)
):
    """Send RCON command to a specific server"""
    instance = docker_mc_manager.get_instance(server_id)

    # Check if server exists and is healthy
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    status = await instance.get_status()
    if status != MCServerStatus.HEALTHY:
        raise HTTPException(
            status_code=409,
            detail=f"Server '{server_id}' must be healthy to send RCON commands (current status: {status})",
        )

    # Send RCON command
    result = await instance.send_command_rcon(rcon_command.command)

    return {"result": result, "command": rcon_command.command}
