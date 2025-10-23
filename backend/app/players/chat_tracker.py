"""Chat and achievement tracking."""

from ..db.database import get_async_session
from ..events.base import PlayerAchievementEvent, PlayerChatMessageEvent
from ..events.dispatcher import EventDispatcher
from ..logger import log_exception, logger
from ..server_tracker.crud import get_server_db_id
from .crud import create_chat_message, get_or_add_player_by_name, upsert_achievement


class ChatTracker:
    """Tracks player chat messages and achievements."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
    ):
        """Initialize chat tracker.

        Args:
            event_dispatcher: Event dispatcher for listening to events
        """
        self.event_dispatcher = event_dispatcher

        # Register event handlers
        self.event_dispatcher.on_player_chat_message(self._handle_chat_message)
        self.event_dispatcher.on_player_achievement(self._handle_achievement)

    @log_exception("Error handling chat message: ")
    async def _handle_chat_message(self, event: PlayerChatMessageEvent) -> None:
        """Handle player chat message event.

        Args:
            event: Chat message event
        """
        async with get_async_session() as session:
            server_db_id = await get_server_db_id(session, event.server_id)
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

            # Save chat message
            await create_chat_message(
                session,
                player.player_db_id,
                server_db_id,
                event.message,
                event.timestamp,
            )

            logger.info(
                f"Saved chat message from {event.player_name} on {event.server_id}"
            )

    @log_exception("Error handling achievement: ")
    async def _handle_achievement(self, event: PlayerAchievementEvent) -> None:
        """Handle player achievement event.

        Args:
            event: Achievement event
        """
        async with get_async_session() as session:
            server_db_id = await get_server_db_id(session, event.server_id)
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

            # Upsert achievement (avoid duplicates)
            await upsert_achievement(
                session,
                player.player_db_id,
                server_db_id,
                event.achievement_name,
                event.timestamp,
            )

            logger.info(
                f"Saved achievement '{event.achievement_name}' for {event.player_name} on {event.server_id}"
            )
