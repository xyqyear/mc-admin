import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserPublic
from app.servers.api_models import ServerInfo

from ...db.database import get_db
from ...dependencies import get_current_user
from ...logger import get_logger
from ...minecraft import get_docker_mc_manager
from ...servers.api_models import ServerListItem
from ...servers.crud import get_active_server_by_id, get_active_servers
from ...servers.queries import get_server_list_item

router = APIRouter(
    prefix="/servers",
    tags=["servers"],
)


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
    logger = get_logger()
    active_rows = await get_active_servers(db)

    if not active_rows:
        return []

    instances = [get_docker_mc_manager().get_instance(row.server_id) for row in active_rows]
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
async def get_server(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get detailed information about a specific server"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    # Get server info
    server_info = await instance.get_server_info()
    record = await get_active_server_by_id(db, server_id)

    return ServerInfo(
        id=server_id,
        server_generation=record.id if record is not None else None,
        name=server_info.name,
        serverType=server_info.server_type,
        gameVersion=server_info.game_version,
        gamePort=server_info.game_port,
        maxMemoryBytes=server_info.max_memory_bytes or 0,
        rconPort=server_info.rcon_port,
        javaVersion=server_info.java_version,
    )
