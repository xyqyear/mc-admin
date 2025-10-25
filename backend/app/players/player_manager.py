"""Player state management."""

import asyncio

from ..db.database import get_async_session
from ..events.base import (
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerSkinUpdateRequestedEvent,
    PlayerUuidDiscoveredEvent,
)
from ..events.dispatcher import EventDispatcher
from ..logger import log_exception, logger
from .crud import (
    get_or_add_player_by_name,
    upsert_player,
)


class PlayerManager:
    """Manages player state and information."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
    ):
        """Initialize player manager.

        Args:
            event_dispatcher: Event dispatcher for listening to events
        """
        self.event_dispatcher = event_dispatcher

        # Register event handlers
        self.event_dispatcher.on_player_uuid_discovered(self._handle_uuid_discovered)
        self.event_dispatcher.on_player_joined(self._handle_player_joined)
        self.event_dispatcher.on_player_left(self._handle_player_left)

    @log_exception("Error handling UUID discovery: ")
    async def _handle_uuid_discovered(self, event: PlayerUuidDiscoveredEvent) -> None:
        """Handle player UUID discovery event.

        Args:
            event: UUID discovery event
        """
        async with get_async_session() as session:
            await upsert_player(session, event.uuid, event.player_name)
            logger.info(f"Updated player UUID: {event.player_name} = {event.uuid}")

    @log_exception("Error handling player join: ")
    async def _handle_player_joined(self, event: PlayerJoinedEvent) -> None:
        """Handle player join event.

        Args:
            event: Player join event
        """
        async with get_async_session() as session:
            # Get or add player by name
            player = await get_or_add_player_by_name(session, event.player_name)
            if player is None:
                logger.warning(
                    f"Player not found and could not be fetched: {event.player_name}"
                )
                return

            logger.info(f"Player joined: {event.player_name} on {event.server_id}")

            # Store player info before session closes
            player_db_id = player.player_db_id
            player_uuid = player.uuid
            player_name = player.current_name

        # Dispatch skin update event outside of database session
        # This triggers skin update for every player join, not just new players
        asyncio.create_task(
            self.event_dispatcher.dispatch_player_skin_update_requested(
                PlayerSkinUpdateRequestedEvent(
                    player_db_id=player_db_id,
                    uuid=player_uuid,
                    player_name=player_name,
                )
            )
        )
        logger.info(f"Dispatched skin update request for {event.player_name}")

    @log_exception("Error handling player leave: ")
    async def _handle_player_left(self, event: PlayerLeftEvent) -> None:
        """Handle player leave event.

        Args:
            event: Player leave event
        """
        async with get_async_session() as session:
            # Get or add player by name
            player = await get_or_add_player_by_name(session, event.player_name)
            if player is None:
                logger.warning(
                    f"Player not found and could not be fetched: {event.player_name}"
                )
                return

            logger.info(f"Player left: {event.player_name} from {event.server_id}")
