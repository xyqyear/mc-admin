"""Session tracking for player game sessions."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_async_session
from ..events.base import PlayerJoinedEvent, PlayerLeftEvent, ServerStoppingEvent
from ..events.dispatcher import EventDispatcher
from ..logger import logger
from ..models import PlayerSession
from ..server_tracker import crud as server_tracker_crud
from .crud import (
    create_session,
    end_session,
    get_all_open_sessions_on_server,
    get_open_session,
    get_or_add_player_by_name,
)


class SessionTracker:
    """Tracks player gaming sessions."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher,
    ):
        """Initialize session tracker.

        Args:
            event_dispatcher: Event dispatcher for listening to events
        """
        self.event_dispatcher = event_dispatcher

        # Register event handlers
        self.event_dispatcher.on_player_joined(self._handle_player_joined)
        self.event_dispatcher.on_player_left(self._handle_player_left)
        self.event_dispatcher.on_server_stopping(self._handle_server_stopping)

    async def _end_player_session(
        self,
        session: AsyncSession,
        player_session: PlayerSession,
        end_timestamp: datetime,
    ) -> None:
        """End a player session.

        This is a shared helper method used by both player leave and server stopping handlers.

        Args:
            session: Database session
            player_session: The session object to end
            end_timestamp: Timestamp when the session ended
        """
        # Calculate session duration
        duration = int((end_timestamp - player_session.joined_at).total_seconds())

        # End session
        await end_session(session, player_session, end_timestamp, duration)

    async def _handle_player_joined(self, event: PlayerJoinedEvent) -> None:
        """Handle player join event - create new session.

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

                # Create new session
                await create_session(
                    session, player.player_db_id, server_db_id, event.timestamp
                )

                logger.debug(
                    f"Created session for {event.player_name} on {event.server_id}"
                )
        except Exception as e:
            logger.error(f"Error in session join handler: {e}", exc_info=True)

    async def _handle_player_left(self, event: PlayerLeftEvent) -> None:
        """Handle player leave event - end session and update playtime.

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

                # Find open session
                open_session = await get_open_session(
                    session, player.player_db_id, server_db_id
                )

                if open_session:
                    # End session using shared helper
                    await self._end_player_session(
                        session, open_session, event.timestamp
                    )

                    duration = int(
                        (event.timestamp - open_session.joined_at).total_seconds()
                    )
                    logger.debug(
                        f"Ended session for {event.player_name} on {event.server_id} ({duration}s)"
                    )
                else:
                    logger.warning(
                        f"No open session found for {event.player_name} on {event.server_id}"
                    )
        except Exception as e:
            logger.error(f"Error in session leave handler: {e}", exc_info=True)

    async def _handle_server_stopping(self, event: ServerStoppingEvent) -> None:
        """Handle server stopping event - end all open sessions.

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

                # Find all open sessions for this server
                open_sessions = await get_all_open_sessions_on_server(
                    session, server_db_id
                )

                # End each session using shared helper
                for open_session in open_sessions:
                    await self._end_player_session(
                        session, open_session, event.timestamp
                    )

                logger.info(
                    f"Ended {len(open_sessions)} sessions for server {event.server_id}"
                )
        except Exception as e:
            logger.error(f"Error in server stopping handler: {e}", exc_info=True)
