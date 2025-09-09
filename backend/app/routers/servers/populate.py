from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager, MCServerStatus
from ...models import UserPublic
from ...utils.decompression import extract_minecraft_server

router = APIRouter(
    prefix="/servers",
    tags=["server-populate"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


class PopulateServerRequest(BaseModel):
    archive_filename: str


@router.post("/{server_id}/populate")
async def populate_server(
    server_id: str,
    populate_request: PopulateServerRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Populate server data directory from an archive file"""
    try:
        instance = mc_manager.get_instance(server_id)

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

        # Extract server files
        archive_path = settings.archive_path / populate_request.archive_filename.lstrip(
            "/"
        )
        await extract_minecraft_server(str(archive_path), str(server_data_dir))

        return {"success": True, "message": "服务器填充完成"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器文件覆盖失败: {str(e)}")
