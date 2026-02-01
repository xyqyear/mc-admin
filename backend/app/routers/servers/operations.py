from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...players import player_system_manager
from ...servers.crud import mark_server_removed

router = APIRouter(
    prefix="/servers",
    tags=["server-operations"],
)


class ServerOperation(BaseModel):
    action: str  # start, stop, restart, up, down


@router.post("/{server_id}/operations")
async def server_operation(
    server_id: str,
    operation: ServerOperation,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Perform operations on a server (start, stop, restart, up, down)"""
    instance = docker_mc_manager.get_instance(server_id)

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
        # Stop log monitoring before removal
        await player_system_manager.stop_server_monitoring(server_id)
        # Mark server as removed in database
        await mark_server_removed(db, server_id, datetime.now(timezone.utc))
        # Remove the server files
        await instance.remove()
    else:
        raise HTTPException(status_code=400, detail=f"Invalid operation: {action}")

    return {"message": f"Server '{server_id}' {action} operation completed"}
