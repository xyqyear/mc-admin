from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...background_tasks import task_manager
from ...background_tasks.types import TaskType
from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import MCServerStatus, docker_mc_manager
from ...models import UserPublic
from ...utils.decompression import extract_minecraft_server

router = APIRouter(
    prefix="/servers",
    tags=["server-populate"],
)


class PopulateServerRequest(BaseModel):
    archive_filename: str


class PopulateServerResponse(BaseModel):
    task_id: str


@router.post("/{server_id}/populate", response_model=PopulateServerResponse)
async def populate_server(
    server_id: str,
    populate_request: PopulateServerRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Populate server data directory from an archive file (background task)"""
    instance = docker_mc_manager.get_instance(server_id)

    # Get server status and validate it's in correct state
    status = await instance.get_status()
    if status == MCServerStatus.REMOVED:
        raise HTTPException(
            status_code=404,
            detail=f"服务器 '{server_id}' 不存在",
        )
    if status not in [MCServerStatus.EXISTS, MCServerStatus.CREATED]:
        raise HTTPException(
            status_code=409,
            detail=f"服务器 '{server_id}' 必须处于 'exists' 或 'created' 状态才能覆盖文件 (当前状态: {status})",
        )

    # Get server data directory path
    server_data_dir = instance.get_data_path()

    # Get archive path
    archive_path = settings.archive_path / populate_request.archive_filename.lstrip("/")

    # Submit as background task
    task_name = f"填充 {server_id}"
    result = task_manager.submit(
        task_type=TaskType.ARCHIVE_EXTRACT,
        name=task_name,
        task_generator=extract_minecraft_server(
            str(archive_path), str(server_data_dir)
        ),
        server_id=server_id,
        cancellable=False,  # Extraction shouldn't be cancelled mid-way
    )

    return PopulateServerResponse(task_id=result.task_id)
