from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...background_tasks import TaskType, task_manager
from ...dependencies import get_current_user
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...servers import rebuild_server_task

router = APIRouter(
    prefix="/servers",
    tags=["server-compose"],
)


class ComposeConfig(BaseModel):
    yaml_content: str


class RebuildResponse(BaseModel):
    task_id: str


@router.get("/{server_id}/compose")
async def get_server_compose(server_id: str, _: UserPublic = Depends(get_current_user)):
    """Get the Docker Compose configuration for a specific server"""
    instance = docker_mc_manager.get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    try:
        # Get compose file content
        compose_content = await instance.get_compose_file()

        return {"yaml_content": compose_content}

    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Compose file not found for server '{server_id}'"
        )


@router.post("/{server_id}/compose", response_model=RebuildResponse)
async def update_server_compose(
    server_id: str,
    compose_config: ComposeConfig,
    _: UserPublic = Depends(get_current_user),
):
    """Update the Docker Compose configuration for a specific server.

    Returns a task_id for tracking the rebuild progress.
    """
    instance = docker_mc_manager.get_instance(server_id)

    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"服务器 '{server_id}' 不存在")

    result = task_manager.submit(
        task_type=TaskType.SERVER_REBUILD,
        name=f"重建 {server_id}",
        task_generator=rebuild_server_task(server_id, compose_config.yaml_content),
        server_id=server_id,
        cancellable=False,
    )

    return RebuildResponse(task_id=result.task_id)
