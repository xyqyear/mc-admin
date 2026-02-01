"""Player status synchronization using RCON."""

import asyncio
from typing import Optional, Set

from ..db.database import get_async_session
from ..dynamic_config import config
from ..events.base import PlayerJoinedEvent, PlayerLeftEvent
from ..events.dispatcher import EventDispatcher
from ..logger import log_exception, logger
from ..minecraft import DockerMCManager, MCServerStatus
from ..servers.crud import get_active_servers_map
from .crud import get_online_player_names_on_server


class PlayerSyncer:
    """Synchronizes player online status using RCON queries."""

    def __init__(
        self,
        mc_manager: DockerMCManager,
        event_dispatcher: EventDispatcher,
    ):
        """Initialize player syncer.

        Args:
            mc_manager: Minecraft Docker manager
            event_dispatcher: Event dispatcher for player status changes
        """
        self.mc_manager = mc_manager
        self.event_dispatcher = event_dispatcher

        self._task: Optional[asyncio.Task] = None
        self._stop_flag = False

    async def start(self) -> None:
        """Start player syncer."""
        logger.info("Starting player syncer...")
        self._stop_flag = False
        self._task = asyncio.create_task(self._validate_loop())
        logger.info("Player syncer started")

    async def stop(self) -> None:
        """Stop player syncer."""
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
        """Validation loop."""
        while not self._stop_flag:
            await self._validate_all_servers()
            await asyncio.sleep(
                config.players.rcon_validation.validation_interval_seconds
            )

    @log_exception("Error validating all servers: ")
    async def _validate_all_servers(self) -> None:
        """Validate player status on all active servers."""
        async with get_async_session() as session:
            # Get all active servers from database
            active_servers = await get_active_servers_map(session)

        # Validate each server with its own session to avoid long transactions
        for server_id, server_db_id in active_servers.items():
            if self._stop_flag:
                break

            await self._validate_server(server_id, server_db_id)

    @log_exception("Error validating server {server_id}: ")
    async def _validate_server(self, server_id: str, server_db_id: int) -> None:
        """Validate player status on a single server.

        Args:
            server_id: Server identifier
            server_db_id: Server database ID
        """
        # Get server instance
        instance = self.mc_manager.get_instance(server_id)

        # Check server status
        status = await instance.get_status()
        if status != MCServerStatus.HEALTHY:
            logger.debug(f"Server {server_id} is not healthy, skipping validation")
            return

        # Get online players from RCON
        try:
            online_players = await instance.list_players()
            online_player_names: Set[str] = set(online_players)
        except Exception as e:
            logger.warning(f"Failed to get player list from {server_id}: {e}")
            return

        # Get online players from database using CRUD function
        async with get_async_session() as session:
            # Get online player names using CRUD function
            db_online_names = await get_online_player_names_on_server(
                session, server_db_id
            )

            # Find discrepancies
            falsely_online = db_online_names - online_player_names
            falsely_offline = online_player_names - db_online_names

            # Correct false positives (marked online but not in RCON)
            if falsely_online:
                logger.warning(
                    f"Correcting {len(falsely_online)} falsely online players on {server_id}: {falsely_online}"
                )
                for player_name in falsely_online:
                    # Dispatch player left event to trigger proper cleanup
                    await self.event_dispatcher.dispatch_player_left(
                        PlayerLeftEvent(
                            server_id=server_id,
                            player_name=player_name,
                        )
                    )

            # Correct false negatives (online in RCON but not in DB)
            if falsely_offline:
                logger.warning(
                    f"Correcting {len(falsely_offline)} falsely offline players on {server_id}: {falsely_offline}"
                )
                for player_name in falsely_offline:
                    # Dispatch player joined event to add them to DB
                    await self.event_dispatcher.dispatch_player_joined(
                        PlayerJoinedEvent(
                            server_id=server_id,
                            player_name=player_name,
                        )
                    )

            logger.debug(
                f"Validated {server_id}: {len(online_player_names)} online, "
                f"{len(falsely_online)} marked offline, {len(falsely_offline)} marked online"
            )
