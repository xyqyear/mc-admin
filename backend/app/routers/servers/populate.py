import asyncio
import json
from dataclasses import dataclass
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager, MCServerStatus
from ...minecraft.utils import async_rmtree
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


@dataclass
class EventData:
    event: str
    data: dict
    error: str | None = None

    def __str__(self) -> str:
        final_data = dict(**self.data, error=self.error) if self.error else self.data
        return f"event: {self.event}\ndata: {json.dumps(final_data).replace('\n', '').replace('\r', '')}\n\n"


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
            last_step = "cleanup"
            try:
                if server_data_dir.exists():
                    for item in server_data_dir.iterdir():
                        if item.is_dir():
                            await async_rmtree(item)
                        else:
                            await asyncio.to_thread(item.unlink)

                    yield str(
                        EventData(
                            event="data",
                            data={
                                "step": "cleanup",
                                "success": True,
                                "message": "已清空数据目录",
                            },
                        )
                    )
                else:
                    server_data_dir.mkdir(parents=True, exist_ok=True)
                    yield str(
                        EventData(
                            event="data",
                            data={
                                "step": "cleanup",
                                "success": True,
                                "message": "已创建数据目录",
                            },
                        )
                    )

                async for step_result in extract_minecraft_server(
                    str(archive_path), str(server_data_dir)
                ):
                    if step_result.success:
                        yield str(
                            EventData(event="data", data=step_result.model_dump())
                        )
                        last_step = step_result.step
                    else:
                        yield str(
                            EventData(
                                event="data", data=step_result.model_dump(), error=step_result.message
                            )
                        )

                # Final completion message
                yield str(
                    EventData(
                        event="data",
                        data={
                            "step": "complete",
                            "success": True,
                            "message": "服务器填充完成",
                        },
                    )
                )

            except Exception as e:
                # Send error as SSE event
                error_message = str(e)
                yield str(
                    EventData(
                        event="data",
                        data={
                            "step": last_step,
                            "success": False,
                            "message": error_message,
                        },
                        error=error_message
                    )
                )

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
