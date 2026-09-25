"""Player status synchronization using RCON."""

import asyncio

from ..db.database import get_async_session
from ..dynamic_config import get_config
from ..logger import get_logger, log_exception
from ..minecraft import MCServerStatus, get_docker_mc_manager
from ..runtime_resources import current_runtime
from ..servers.crud import get_active_servers_map
from .service import PlayerService, get_player_service


class PlayerSyncer:
    """Periodically reconcile DB online state with RCON ``list``."""

    def __init__(self, players: PlayerService | None = None):
        self._players = players
        self._task: asyncio.Task | None = None
        self._stop_flag = False

    @property
    def players(self) -> PlayerService:
        return self._players if self._players is not None else get_player_service()

    async def start(self) -> None:
        logger = get_logger()
        logger.info("Starting player syncer...")
        self._stop_flag = False
        self._task = asyncio.create_task(self._validate_loop())
        logger.info("Player syncer started")

    async def stop(self) -> None:
        logger = get_logger()
        logger.info("Stopping player syncer...")
        self._stop_flag = True

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Player syncer stopped")

    async def _validate_loop(self) -> None:
        while not self._stop_flag:
            await self.validate_all_servers()
            await asyncio.sleep(
                get_config().players.rcon_validation.validation_interval_seconds
            )

    @log_exception("Error validating all servers: ")
    async def validate_all_servers(self) -> None:
        async with get_async_session() as session:
            active_servers = await get_active_servers_map(session)

        for server_id, server_db_id in active_servers.items():
            if self._stop_flag:
                break

            await self._validate_server(server_id, server_db_id)

    @log_exception("Error validating server {server_id}: ")
    async def _validate_server(self, server_id: str, server_db_id: int) -> None:
        logger = get_logger()
        instance = get_docker_mc_manager().get_instance(server_id)

        status = await instance.get_status()
        if status != MCServerStatus.HEALTHY:
            logger.debug(f"Server {server_id} is not healthy, skipping validation")
            return

        try:
            online_players = await instance.list_players()
        except Exception as e:
            logger.warning(f"Failed to get player list from {server_id}: {e}", exc_info=True)
            return

        await self.players.reconcile_online(server_id, server_db_id, online_players)


def get_player_syncer() -> PlayerSyncer:
    return current_runtime().resource('player_syncer')
