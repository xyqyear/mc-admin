import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ...dependencies import get_current_user
from ...minecraft import MCInstance, docker_mc_manager
from ...models import UserPublic

RCON_COMMAND_TIMEOUT = 10.0

MinecraftColor = Literal[
    "black",
    "dark_blue",
    "dark_green",
    "dark_aqua",
    "dark_red",
    "dark_purple",
    "gold",
    "gray",
    "dark_gray",
    "blue",
    "green",
    "aqua",
    "red",
    "light_purple",
    "yellow",
    "white",
]

router = APIRouter(
    prefix="/servers",
    tags=["server-rcon"],
)


class RconCommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=1000)


class RconCommandResponse(BaseModel):
    output: str


class ServerMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    target_player: str | None = Field(default=None, pattern=r"^\w{1,16}$")
    color: MinecraftColor = "yellow"


async def _get_rcon_ready_instance(server_id: str) -> MCInstance:
    instance = docker_mc_manager.get_instance(server_id)

    if not await instance.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"服务器 '{server_id}' 不存在",
        )

    if not await instance.healthy():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="服务器当前无法执行命令（未在健康状态）",
        )

    return instance


async def _run_rcon_command(instance: MCInstance, command: str) -> str:
    try:
        return await asyncio.wait_for(
            instance.send_command_rcon(command),
            timeout=RCON_COMMAND_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="命令执行超时",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )


@router.post("/{server_id}/rcon", response_model=RconCommandResponse)
async def execute_rcon_command(
    server_id: str,
    request: RconCommandRequest,
    _: UserPublic = Depends(get_current_user),
):
    instance = await _get_rcon_ready_instance(server_id)
    output = await _run_rcon_command(instance, request.command)
    return RconCommandResponse(output=output)


@router.post("/{server_id}/message", status_code=status.HTTP_204_NO_CONTENT)
async def send_server_message(
    server_id: str,
    request: ServerMessageRequest,
    _: UserPublic = Depends(get_current_user),
):
    instance = await _get_rcon_ready_instance(server_id)
    target = request.target_player or "@a"

    for line in request.message.splitlines():
        if not line:
            continue
        component = json.dumps(
            {"text": line, "color": request.color},
            ensure_ascii=False,
        )
        await _run_rcon_command(instance, f"tellraw {target} {component}")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
