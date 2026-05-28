"""Player status synchronization using RCON."""

import asyncio
from typing import Optional, Set

from ..db.database import get_async_session
from ..dynamic_config import config
from ..logger import log_exception, logger
from ..minecraft import MCServerStatus, docker_mc_manager
from ..servers.crud import get_active_servers_map
from .crud import get_online_player_names_on_server
from .name_filters import is_ignored_player_name
from .tracking import process_player_join, process_player_left


class PlayerSyncer:
    """Periodically reconcile DB online state with RCON ``list``."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stop_flag = False

    async def start(self) -> None:
        logger.info("Starting player syncer...")
        self._stop_flag = False
        self._task = asyncio.create_task(self._validate_loop())
        logger.info("Player syncer started")

    async def stop(self) -> None:
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
                config.players.rcon_validation.validation_interval_seconds
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
        instance = docker_mc_manager.get_instance(server_id)

        status = await instance.get_status()
        if status != MCServerStatus.HEALTHY:
            logger.debug(f"Server {server_id} is not healthy, skipping validation")
            return

        try:
            online_players = await instance.list_players()
            online_player_names: Set[str] = {
                name for name in online_players if not is_ignored_player_name(name)
            }
        except Exception as e:
            logger.warning(f"Failed to get player list from {server_id}: {e}")
            return

        async with get_async_session() as session:
            db_online_names = await get_online_player_names_on_server(
                session, server_db_id
            )

            falsely_online = db_online_names - online_player_names
            falsely_offline = online_player_names - db_online_names

            if falsely_online:
                logger.warning(
                    f"Correcting {len(falsely_online)} falsely online players on {server_id}: {falsely_online}"
                )
                for player_name in falsely_online:
                    await process_player_left(server_id, player_name)

            if falsely_offline:
                logger.warning(
                    f"Correcting {len(falsely_offline)} falsely offline players on {server_id}: {falsely_offline}"
                )
                for player_name in falsely_offline:
                    await process_player_join(server_id, player_name)

            logger.debug(
                f"Validated {server_id}: {len(online_player_names)} online, "
                f"{len(falsely_online)} marked offline, {len(falsely_offline)} marked online"
            )


player_syncer = PlayerSyncer()
