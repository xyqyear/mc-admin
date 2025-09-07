from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["server-operations"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


class ServerOperation(BaseModel):
    action: str  # start, stop, restart, up, down


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