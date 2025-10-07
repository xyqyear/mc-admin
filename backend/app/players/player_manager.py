"""Player state management."""

import asyncio

from ..db.database import get_async_session
from ..events.base import (
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerSkinUpdateRequestedEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from ..events.dispatcher import EventDispatcher
from ..logger import logger
from ..server_tracker import crud as server_tracker_crud
from .crud import (
    get_or_add_player_by_name,
    set_all_players_offline_on_server,
    set_player_offline,
    update_player_last_seen,
    upsert_player,
    upsert_player_online_status,
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
        self.event_dispatcher.on_server_stopping(self._handle_server_stopping)

    async def _handle_uuid_discovered(self, event: PlayerUuidDiscoveredEvent) -> None:
        """Handle player UUID discovery event.

        Args:
            event: UUID discovery event
        """
        try:
            async with get_async_session() as session:
                try:
                    await upsert_player(session, event.uuid, event.player_name)
                    logger.debug(
                        f"Updated player UUID: {event.player_name} = {event.uuid}"
                    )
                except Exception as e:
                    logger.error(f"Error handling UUID discovery: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in UUID discovery handler: {e}", exc_info=True)

    async def _handle_player_joined(self, event: PlayerJoinedEvent) -> None:
        """Handle player join event.

        Args:
            event: Player join event
        """
        try:
            async with get_async_session() as session:
                server_db_id = await server_tracker_crud.get_server_db_id(
                    session, event.server_id
                )
                if server_db_id is None:
                    logger.warning(f"Server not found in tracker: {event.server_id}")
                    return

                # Get or add player by name
                player = await get_or_add_player_by_name(session, event.player_name)
                if player is None:
                    logger.warning(
                        f"Player not found and could not be fetched: {event.player_name}"
                    )
                    return

                # Update online status
                await upsert_player_online_status(
                    session, player.player_db_id, server_db_id, True, event.timestamp
                )

                # Update last_seen
                await update_player_last_seen(
                    session, player.player_db_id, event.timestamp
                )

                logger.debug(f"Player joined: {event.player_name} on {event.server_id}")

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
            logger.debug(f"Dispatched skin update request for {event.player_name}")
        except Exception as e:
            logger.error(f"Error in player join handler: {e}", exc_info=True)

    async def _handle_player_left(self, event: PlayerLeftEvent) -> None:
        """Handle player leave event.

        Args:
            event: Player leave event
        """
        try:
            async with get_async_session() as session:
                server_db_id = await server_tracker_crud.get_server_db_id(
                    session, event.server_id
                )
                if server_db_id is None:
                    logger.warning(f"Server not found in tracker: {event.server_id}")
                    return

                # Get or add player by name
                player = await get_or_add_player_by_name(session, event.player_name)
                if player is None:
                    logger.warning(
                        f"Player not found and could not be fetched: {event.player_name}"
                    )
                    return

                # Set player offline
                await set_player_offline(
                    session, player.player_db_id, server_db_id, event.timestamp
                )

                logger.debug(f"Player left: {event.player_name} from {event.server_id}")
        except Exception as e:
            logger.error(f"Error in player leave handler: {e}", exc_info=True)

    async def _handle_server_stopping(self, event: ServerStoppingEvent) -> None:
        """Handle server stopping event - mark all players offline.

        Args:
            event: Server stopping event
        """
        try:
            async with get_async_session() as session:
                server_db_id = await server_tracker_crud.get_server_db_id(
                    session, event.server_id
                )
                if server_db_id is None:
                    logger.warning(f"Server not found in tracker: {event.server_id}")
                    return

                # Mark all players offline for this server
                count = await set_all_players_offline_on_server(
                    session, server_db_id, event.timestamp
                )

                logger.info(
                    f"Marked {count} players offline for server {event.server_id}"
                )
        except Exception as e:
            logger.error(f"Error in server stopping handler: {e}", exc_info=True)
