"""System heartbeat and crash recovery."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..db.database import get_async_session
from ..dynamic_config import config
from ..logger import log_exception, logger
from .crud import get_online_players_with_names_grouped_by_server
from .crud.heartbeat import get_heartbeat, upsert_heartbeat


class HeartbeatManager:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stop_flag = False

    async def start(self) -> None:
        logger.info("Starting heartbeat manager...")

        await self._check_crash()

        self._stop_flag = False
        self._task = asyncio.create_task(self._heartbeat_loop())

        logger.info("Heartbeat manager started")

    async def stop(self) -> None:
        logger.info("Stopping heartbeat manager...")
        self._stop_flag = True

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Heartbeat manager stopped")

    @log_exception("Error checking for crash: ")
    async def _check_crash(self) -> None:
        async with get_async_session() as session:
            heartbeat = await get_heartbeat(session)

            if heartbeat is None:
                logger.info("No previous heartbeat found (first startup)")
                return

            now = datetime.now(timezone.utc)
            time_since_heartbeat = now - heartbeat.timestamp

            crash_threshold = timedelta(
                minutes=config.players.heartbeat.crash_threshold_minutes
            )
            if time_since_heartbeat >= crash_threshold:
                logger.warning(
                    f"System crash detected! Last heartbeat was {time_since_heartbeat.total_seconds():.0f} seconds ago"
                )
                await self._recover_from_crash(
                    session,
                    heartbeat.timestamp,
                    time_since_heartbeat.total_seconds(),
                )
            else:
                logger.info(
                    f"Normal restart detected (last heartbeat {time_since_heartbeat.total_seconds():.0f}s ago)"
                )

    @log_exception("Error during crash recovery: ")
    async def _recover_from_crash(
        self, session, crash_timestamp: datetime, time_since_crash: float
    ) -> None:
        """End each open session via ``process_player_left`` then resync via RCON."""
        from .player_syncer import player_syncer
        from .tracking import process_player_left

        logger.info("Starting crash recovery...")

        players_by_server = await get_online_players_with_names_grouped_by_server(
            session
        )

        total_players = sum(len(players) for players in players_by_server.values())

        logger.info(
            f"Found {total_players} online players across {len(players_by_server)} servers to process during crash recovery"
        )

        for server_id, player_names in players_by_server.items():
            logger.info(
                f"Processing {len(player_names)} players on server {server_id}: {player_names}"
            )
            for player_name in player_names:
                await process_player_left(
                    server_id, player_name, "System crash", crash_timestamp
                )

        logger.info(
            f"Crash recovery completed - processed {total_players} player departures"
        )

        logger.info(
            f"System crash event - triggering player sync "
            f"(crash at {crash_timestamp}, {time_since_crash:.0f}s ago)"
        )
        await player_syncer.validate_all_servers()

    async def _heartbeat_loop(self) -> None:
        while not self._stop_flag:
            await self._update_heartbeat()
            await asyncio.sleep(config.players.heartbeat.heartbeat_interval_seconds)

    @log_exception("Error updating heartbeat: ")
    async def _update_heartbeat(self) -> None:
        async with get_async_session() as session:
            await upsert_heartbeat(session, datetime.now(timezone.utc))
            logger.debug("Updated heartbeat")


heartbeat_manager = HeartbeatManager()
