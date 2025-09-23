from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...dependencies import get_current_user
from ...minecraft import MCServerStatus, docker_mc_manager
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["server-compose"],
)


class ComposeConfig(BaseModel):
    yaml_content: str


@router.get("/{server_id}/compose")
async def get_server_compose(server_id: str, _: UserPublic = Depends(get_current_user)):
    """Get the Docker Compose configuration for a specific server"""
    try:
        instance = docker_mc_manager.get_instance(server_id)

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
        instance = docker_mc_manager.get_instance(server_id)

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
