import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...logger import logger
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...servers.crud import get_active_servers
from .utils.server_list import ServerListItem, get_server_list_item

router = APIRouter(
    prefix="/servers",
    tags=["servers"],
)


# Pydantic models for API responses
class ServerInfo(BaseModel):
    id: str
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    maxMemoryBytes: int
    rconPort: int
    javaVersion: int


class ServerStatus(BaseModel):
    status: str


@router.get("/", response_model=list[ServerListItem])
async def get_servers(
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get list of all servers with basic info only (no status or runtime data).

    Source of truth is the DB (`Server` rows with status=ACTIVE). Per-server
    compose reads run in parallel via asyncio.gather; ACTIVE rows whose
    compose has drifted away are filtered out with a per-row warning so the
    operator can correlate the gap with the sync endpoint without UI silence.
    """
    active_rows = await get_active_servers(db)

    if not active_rows:
        return []

    instances = [docker_mc_manager.get_instance(row.server_id) for row in active_rows]
    server_data_tasks = [get_server_list_item(instance) for instance in instances]

    results = await asyncio.gather(*server_data_tasks, return_exceptions=True)

    valid_servers: list[ServerListItem] = []
    for row, result in zip(active_rows, results):
        if isinstance(result, BaseException):
            logger.warning(
                f"GET /servers: skipping '{row.server_id}' (cannot read compose): {result}"
            )
            continue
        valid_servers.append(result)

    return valid_servers


@router.get("/{server_id}", response_model=ServerInfo)
async def get_server(server_id: str, _: UserPublic = Depends(get_current_user)):
    """Get detailed information about a specific server"""
    instance = docker_mc_manager.get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    # Get server info
    server_info = await instance.get_server_info()

    return ServerInfo(
        id=server_id,
        name=server_info.name,
        serverType=server_info.server_type,
        gameVersion=server_info.game_version,
        gamePort=server_info.game_port,
        maxMemoryBytes=server_info.max_memory_bytes or 0,
        rconPort=server_info.rcon_port,
        javaVersion=server_info.java_version,
    )


@router.get("/{server_id}/status", response_model=ServerStatus)
async def get_server_status(server_id: str, _: UserPublic = Depends(get_current_user)):
    """Get current status of a specific server"""
    instance = docker_mc_manager.get_instance(server_id)
    status = await instance.get_status()

    return ServerStatus(status=status.name)
