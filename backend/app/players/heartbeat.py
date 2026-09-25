"""System heartbeat and crash recovery."""

import asyncio
from datetime import UTC, datetime, timedelta

from ..db.database import get_async_session
from ..dynamic_config import get_config
from ..logger import get_logger, log_exception
from ..runtime_resources import current_runtime
from .crud.heartbeat import get_heartbeat, upsert_heartbeat
from .service import PlayerService, get_player_service


class HeartbeatManager:
    def __init__(self, players: PlayerService | None = None):
        self._players = players
        self._task: asyncio.Task | None = None
        self._stop_flag = False

    @property
    def players(self) -> PlayerService:
        return self._players if self._players is not None else get_player_service()

    async def start(self) -> None:
        logger = get_logger()
        logger.info("Starting heartbeat manager...")

        await self._check_crash()

        self._stop_flag = False
        self._task = asyncio.create_task(self._heartbeat_loop())

        logger.info("Heartbeat manager started")

    async def stop(self) -> None:
        logger = get_logger()
        logger.info("Stopping heartbeat manager...")
        self._stop_flag = True

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Heartbeat manager stopped")

    async def _check_crash(self) -> None:
        logger = get_logger()
        async with get_async_session() as session:
            heartbeat = await get_heartbeat(session)
            timestamp = heartbeat.timestamp if heartbeat is not None else None
        if timestamp is None:
            logger.info("No previous heartbeat found (first startup)")
            return
        elapsed = datetime.now(UTC) - timestamp
        threshold = timedelta(minutes=get_config().players.heartbeat.crash_threshold_minutes)
        if elapsed < threshold:
            logger.info(f"Normal restart detected (last heartbeat {elapsed.total_seconds():.0f}s ago)")
            return
        logger.warning(f"System crash detected! Last heartbeat was {elapsed.total_seconds():.0f} seconds ago")
        await self.players.recover_crash(timestamp)
        from .player_syncer import get_player_syncer

        await get_player_syncer().validate_all_servers()

    async def _heartbeat_loop(self) -> None:
        while not self._stop_flag:
            await self._update_heartbeat()
            await asyncio.sleep(get_config().players.heartbeat.heartbeat_interval_seconds)

    @log_exception("Error updating heartbeat: ")
    async def _update_heartbeat(self) -> None:
        logger = get_logger()
        async with get_async_session() as session:
            await upsert_heartbeat(session, datetime.now(UTC))
            logger.debug("Updated heartbeat")


def get_heartbeat_manager() -> HeartbeatManager:
    return current_runtime().resource('heartbeat_manager')
