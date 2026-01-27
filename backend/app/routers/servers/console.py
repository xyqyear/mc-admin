from fastapi import APIRouter, Depends, Query, WebSocket

from ...dependencies import get_websocket_user
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...websocket.console import ConsoleWebSocketHandler

router = APIRouter(
    prefix="/servers",
    tags=["console"],
)


@router.websocket("/{server_id}/console")
async def console_websocket(
    websocket: WebSocket,
    server_id: str,
    cols: int = Query(...),
    rows: int = Query(...),
    _: UserPublic = Depends(get_websocket_user),
):
    instance = docker_mc_manager.get_instance(server_id)
    handler = ConsoleWebSocketHandler(websocket, instance)
    await handler.handle_connection(server_id, cols, rows)
