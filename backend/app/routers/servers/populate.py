import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager, MCServerStatus
from ...minecraft.utils import async_rmtree
from ...models import UserPublic
from ...utils.decompression import extract_minecraft_server, DecompressionError

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
    """Populate server data directory from an archive file with SSE progress streaming"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get server status and validate it's in correct state
        status = await instance.get_status()
        if status not in [MCServerStatus.EXISTS, MCServerStatus.CREATED]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' must be in 'exists' or 'created' status to populate (current status: {status})",
            )

        # Construct archive file path
        archive_path = settings.archive_path / populate_request.archive_filename
        if not archive_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Archive file '{populate_request.archive_filename}' not found",
            )

        # Get server data directory path
        server_data_dir = settings.server_path / server_id / "data"
        
        async def generate_progress() -> AsyncGenerator[str, None]:
            try:
                # Step 1: Clear data directory (but keep the directory itself)
                if server_data_dir.exists():
                    # Remove all contents in data directory
                    for item in server_data_dir.iterdir():
                        if item.is_dir():
                            await async_rmtree(item)
                        else:
                            await asyncio.to_thread(item.unlink)
                    
                    yield "data: {\"step\": \"cleanup\", \"success\": true, \"message\": \"已清空数据目录\", \"error_details\": null}\n\n"
                else:
                    # Create data directory if it doesn't exist
                    server_data_dir.mkdir(parents=True, exist_ok=True)
                    yield "data: {\"step\": \"cleanup\", \"success\": true, \"message\": \"已创建数据目录\", \"error_details\": null}\n\n"

                # Step 2: Extract archive to data directory using the generator
                async for step_result in extract_minecraft_server(
                    str(archive_path), str(server_data_dir)
                ):
                    # Convert DecompressionStepResult to JSON and send as SSE
                    step_json = step_result.model_dump_json()
                    yield f"data: {step_json}\n\n"

                # Final completion message
                yield "data: {\"step\": \"complete\", \"success\": true, \"message\": \"服务器填充完成\", \"error_details\": null}\n\n"
                
            except Exception as e:
                # Send error as SSE event
                error_message = str(e).replace('"', '\\"')  # Escape quotes in error message
                if isinstance(e, DecompressionError):
                    step = e.step
                    error_details_str = str(e.error_details).replace('"', '\\"') if e.error_details else None
                else:
                    step = "unknown"
                    error_details_str = None
                
                # Format error_details for JSON
                error_details_json = "null" if error_details_str is None else f'"{error_details_str}"'
                
                yield f'data: {{"step": "{step}", "success": false, "message": "{error_message}", "error_details": {error_details_json}}}\\n\\n'

        return StreamingResponse(
            generate_progress(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to populate server: {str(e)}"
        )