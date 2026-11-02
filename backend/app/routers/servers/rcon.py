import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.schemas import UserPublic
from app.servers.api_models import (
    RconCommandRequest,
    RconCommandResponse,
    ServerMessageRequest,
)

from ...dependencies import get_current_user
from ...minecraft import MCInstance, get_docker_mc_manager
from ...minecraft.docker.commands import RCON_TIMEOUT, ServerMissing, ServerUnavailable

RCON_COMMAND_TIMEOUT = RCON_TIMEOUT


router = APIRouter(
    prefix="/servers",
    tags=["server-rcon"],
)


async def _run_rcon_command(instance: MCInstance, command: str | None) -> str:
    try:
        if command is None:
            await asyncio.wait_for(instance.get_command_container(), timeout=RCON_COMMAND_TIMEOUT)
            return ""
        return await asyncio.wait_for(
            instance.send_command_rcon(command),
            timeout=RCON_COMMAND_TIMEOUT,
        )
    except ServerMissing as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ServerUnavailable as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="命令执行超时",
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="命令执行失败，执行结果可能未知",
        )


@router.post("/{server_id}/rcon", response_model=RconCommandResponse)
async def execute_rcon_command(
    server_id: str,
    request: RconCommandRequest,
    _: UserPublic = Depends(get_current_user),
):
    instance = get_docker_mc_manager().get_instance(server_id)
    output = await _run_rcon_command(instance, request.command)
    return RconCommandResponse(output=output)


@router.post("/{server_id}/message", status_code=status.HTTP_204_NO_CONTENT)
async def send_server_message(
    server_id: str,
    request: ServerMessageRequest,
    _: UserPublic = Depends(get_current_user),
):
    instance = get_docker_mc_manager().get_instance(server_id)
    target = request.target_player or "@a"
    lines = [line for line in request.message.splitlines() if line]
    if not lines:
        await _run_rcon_command(instance, None)

    for line in lines:
        component = json.dumps(
            {"text": line, "color": request.color},
            ensure_ascii=False,
        )
        await _run_rcon_command(instance, f"tellraw {target} {component}")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
