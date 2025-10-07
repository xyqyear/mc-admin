"""RCON-based player status validation."""

import asyncio
from typing import Optional, Set

from ..db.database import get_async_session
from ..dynamic_config import config
from ..events.base import PlayerJoinedEvent, PlayerLeftEvent
from ..events.dispatcher import EventDispatcher
from ..logger import logger
from ..minecraft import DockerMCManager, MCServerStatus
from ..server_tracker import ServerTracker
from ..server_tracker.crud import get_active_servers_map
from .crud import get_online_players_on_server


class RCONValidator:
    """Validates player online status using RCON queries."""

    def __init__(
        self,
        mc_manager: DockerMCManager,
        server_tracker: ServerTracker,
        event_dispatcher: EventDispatcher,
    ):
        """Initialize RCON validator.

        Args:
            mc_manager: Minecraft Docker manager
            server_tracker: Server tracker for getting active servers
            event_dispatcher: Event dispatcher for player status changes
        """
        self.mc_manager = mc_manager
        self.server_tracker = server_tracker
        self.event_dispatcher = event_dispatcher

        self._task: Optional[asyncio.Task] = None
        self._stop_flag = False

    async def start(self) -> None:
        """Start RCON validator."""
        logger.info("Starting RCON validator...")
        self._stop_flag = False
        self._task = asyncio.create_task(self._validate_loop())
        logger.info("RCON validator started")

    async def stop(self) -> None:
        """Stop RCON validator."""
        logger.info("Stopping RCON validator...")
        self._stop_flag = True

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("RCON validator stopped")

    async def _validate_loop(self) -> None:
        """Validation loop."""
        while not self._stop_flag:
            try:
                await self._validate_all_servers()
            except Exception as e:
                logger.error(f"Error in RCON validation loop: {e}", exc_info=True)

            # Sleep for validation interval
            await asyncio.sleep(
                config.players.rcon_validation.validation_interval_seconds
            )

    async def _validate_all_servers(self) -> None:
        """Validate player status on all active servers."""
        try:
            async with get_async_session() as session:
                # Get all active servers from database
                active_servers = await get_active_servers_map(session)

            # Validate each server with its own session to avoid long transactions
            for server_id, server_db_id in active_servers.items():
                if self._stop_flag:
                    break

                await self._validate_server(server_id, server_db_id)

        except Exception as e:
            logger.error(f"Error validating servers: {e}", exc_info=True)

    async def _validate_server(self, server_id: str, server_db_id: int) -> None:
        """Validate player status on a single server.

        Args:
            server_id: Server identifier
            server_db_id: Server database ID
        """
        try:
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

            # Get online players from database
            async with get_async_session() as session:
                try:
                    db_online = await get_online_players_on_server(
                        session, server_db_id
                    )

                    db_online_names = {player.current_name for _, player in db_online}

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
                except Exception as e:
                    logger.error(
                        f"Error validating server {server_id}: {e}", exc_info=True
                    )

        except Exception as e:
            logger.error(
                f"Error in server validation for {server_id}: {e}", exc_info=True
            )
