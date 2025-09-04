from fastapi import APIRouter, Depends, WebSocket

from ...config import settings
from ...dependencies import get_websocket_user
from ...minecraft import DockerMCManager
from ...models import UserPublic
from ...websocket.console import ConsoleWebSocketHandler

router = APIRouter(
    prefix="/servers",
    tags=["console"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


@router.websocket("/{server_id}/console")
async def console_websocket(
    websocket: WebSocket, server_id: str, _: UserPublic = Depends(get_websocket_user)
):
    instance = mc_manager.get_instance(server_id)
    handler = ConsoleWebSocketHandler(websocket, instance)
    await handler.handle_connection(server_id)