"""Chat and achievement tracking."""

from ..db.database import get_async_session
from ..events.base import PlayerAchievementEvent, PlayerChatMessageEvent
from ..events.dispatcher import EventDispatcher
from ..logger import log_exception, logger
from ..servers.crud import get_server_db_id
from .crud import (
    create_chat_message,
    get_all_player_names_with_ids,
    get_or_add_player_by_name,
    upsert_achievement,
)


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

            # Get all player names and sort by length (longest first)
            # This prevents shorter names from matching when they're part of longer names
            all_players = await get_all_player_names_with_ids(session)
            all_players_sorted = sorted(
                all_players, key=lambda x: len(x[0]), reverse=True
            )

            # Try to find a player name in the achievement text
            # Match from longest to shortest to avoid partial matches
            matched_player_db_id = None
            matched_player_name = None

            for player_name, player_db_id in all_players_sorted:
                if player_name in event.player_name:
                    matched_player_db_id = player_db_id
                    matched_player_name = player_name
                    break

            if matched_player_db_id is None:
                logger.warning(
                    f"No known player found in achievement text: '{event.player_name}'"
                )
                return

            logger.debug(
                f"Matched player '{matched_player_name}' in achievement text '{event.player_name}'"
            )

            # Upsert achievement (avoid duplicates)
            await upsert_achievement(
                session,
                matched_player_db_id,
                server_db_id,
                event.achievement_name,
                event.timestamp,
            )

            logger.info(
                f"Saved achievement '{event.achievement_name}' for {matched_player_name} on {event.server_id}"
            )
