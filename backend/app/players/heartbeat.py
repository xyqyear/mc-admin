"""System heartbeat and crash recovery."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..db.database import get_async_session
from ..dynamic_config import config
from ..events.base import PlayerLeftEvent, SystemCrashDetectedEvent
from ..events.dispatcher import EventDispatcher
from ..logger import logger
from .crud import get_online_players_grouped_by_server
from .crud.heartbeat import get_heartbeat, upsert_heartbeat


class HeartbeatManager:
    """Manages system heartbeat and crash recovery."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize heartbeat manager.

        Args:
            event_dispatcher: Event dispatcher for crash detection events
        """
        self.event_dispatcher = event_dispatcher
        self._task: Optional[asyncio.Task] = None
        self._stop_flag = False

    async def start(self) -> None:
        """Start heartbeat manager."""
        logger.info("Starting heartbeat manager...")

        # Check for crash on startup
        await self._check_crash()

        # Start heartbeat loop
        self._stop_flag = False
        self._task = asyncio.create_task(self._heartbeat_loop())

        logger.info("Heartbeat manager started")

    async def stop(self) -> None:
        """Stop heartbeat manager."""
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
        """Check if system crashed and perform recovery."""
        try:
            async with get_async_session() as session:
                try:
                    # Get last heartbeat
                    heartbeat = await get_heartbeat(session)

                    if heartbeat is None:
                        logger.info("No previous heartbeat found (first startup)")
                        return

                    # Check if heartbeat is stale
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
                except Exception as e:
                    logger.error(f"Error checking for crash: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in crash check: {e}", exc_info=True)

    async def _recover_from_crash(
        self, session, crash_timestamp: datetime, time_since_crash: float
    ) -> None:
        """Recover from system crash.

        Triggers PlayerLeftEvent for each online player to ensure proper cleanup
        including session ending and playtime calculation.

        Args:
            session: Database session
            crash_timestamp: Timestamp of the crash (last heartbeat time)
            time_since_crash: Seconds since the crash occurred
        """
        try:
            logger.info("Starting crash recovery...")

            # Get all online players grouped by server
            players_by_server = await get_online_players_grouped_by_server(session)

            # Calculate total player count
            total_players = sum(len(players) for players in players_by_server.values())

            logger.info(
                f"Found {total_players} online players across {len(players_by_server)} servers to process during crash recovery"
            )

            # Dispatch PlayerLeftEvent for each online player
            # This ensures proper cleanup: session ending, playtime calculation, etc.
            for server_id, player_names in players_by_server.items():
                logger.info(
                    f"Dispatching PlayerLeftEvent for {len(player_names)} players on server {server_id}: {player_names}"
                )
                for player_name in player_names:
                    await self.event_dispatcher.dispatch_player_left(
                        PlayerLeftEvent(
                            server_id=server_id,
                            player_name=player_name,
                            reason="System crash",
                            timestamp=crash_timestamp,
                        )
                    )

            logger.info(
                f"Crash recovery completed - dispatched {total_players} PlayerLeftEvent events"
            )

            # Dispatch crash detected event to trigger RCON validation
            await self.event_dispatcher.dispatch_system_crash_detected(
                SystemCrashDetectedEvent(
                    crash_timestamp=crash_timestamp,
                    time_since_crash=time_since_crash,
                )
            )

        except Exception as e:
            logger.error(f"Error in crash recovery: {e}", exc_info=True)

    async def _heartbeat_loop(self) -> None:
        """Heartbeat update loop."""
        while not self._stop_flag:
            try:
                await self._update_heartbeat()
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)

            # Sleep for heartbeat interval
            await asyncio.sleep(config.players.heartbeat.heartbeat_interval_seconds)

    async def _update_heartbeat(self) -> None:
        """Update system heartbeat."""
        try:
            async with get_async_session() as session:
                try:
                    # Update the single heartbeat record
                    await upsert_heartbeat(session, datetime.now(timezone.utc))
                    logger.debug("Updated heartbeat")
                except Exception as e:
                    logger.error(f"Error updating heartbeat: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in heartbeat update: {e}", exc_info=True)
