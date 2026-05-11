from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...servers.lifecycle import RemoveServerResult, remove_server_full

router = APIRouter(
    prefix="/servers",
    tags=["server-operations"],
)


class ServerOperation(BaseModel):
    action: str  # start, stop, restart, up, down, remove


@router.post("/{server_id}/operations")
async def server_operation(
    server_id: str,
    operation: ServerOperation,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Perform operations on a server (start, stop, restart, up, down, remove).

    For action=remove, returns a RemoveServerResult with counts of cancelled
    cronjobs and closed sessions. For other actions, returns a simple
    message object.
    """
    instance = docker_mc_manager.get_instance(server_id)

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
        result: RemoveServerResult = await remove_server_full(db, server_id)
        return result
    else:
        raise HTTPException(status_code=400, detail=f"Invalid operation: {action}")

    return {"message": f"Server '{server_id}' {action} operation completed"}
