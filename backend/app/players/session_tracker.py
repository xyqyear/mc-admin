"""Session tracking for player game sessions."""

from ..db.database import get_async_session
from ..events.base import PlayerJoinedEvent, PlayerLeftEvent, ServerStoppingEvent
from ..events.dispatcher import EventDispatcher
from ..logger import log_exception, logger
from ..servers import crud as server_crud
from .crud import (
    end_all_open_sessions,
    end_all_open_sessions_on_server,
    get_or_add_player_by_name,
    get_or_create_session,
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

    @log_exception("Error handling player joined event: ")
    async def _handle_player_joined(self, event: PlayerJoinedEvent) -> None:
        """Handle player join event - create new session or reuse existing open session.

        Args:
            event: Player join event
        """
        async with get_async_session() as session:
            server_db_id = await server_crud.get_server_db_id(session, event.server_id)
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

            # Get or create session (will reuse existing open session if exists)
            player_session = await get_or_create_session(
                session, player.player_db_id, server_db_id, event.timestamp
            )

            if player_session.joined_at < event.timestamp:
                logger.debug(
                    f"Reused existing session for {event.player_name} on {event.server_id}"
                )
            else:
                logger.debug(
                    f"Created new session for {event.player_name} on {event.server_id}"
                )

    @log_exception("Error handling player left event: ")
    async def _handle_player_left(self, event: PlayerLeftEvent) -> None:
        """Handle player leave event - end all open sessions.

        Args:
            event: Player leave event
        """
        async with get_async_session() as session:
            server_db_id = await server_crud.get_server_db_id(session, event.server_id)
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

            # End all open sessions for this player on this server
            count = await end_all_open_sessions(
                session, player.player_db_id, server_db_id, event.timestamp
            )

            if count > 0:
                logger.debug(
                    f"Ended {count} session(s) for {event.player_name} on {event.server_id}"
                )
            else:
                logger.warning(
                    f"No open sessions found for {event.player_name} on {event.server_id}"
                )

    @log_exception("Error handling server stopping event: ")
    async def _handle_server_stopping(self, event: ServerStoppingEvent) -> None:
        """Handle server stopping event - end all open sessions on the server.

        Args:
            event: Server stopping event
        """
        async with get_async_session() as session:
            server_db_id = await server_crud.get_server_db_id(session, event.server_id)
            if server_db_id is None:
                logger.warning(f"Server not found in tracker: {event.server_id}")
                return

            # End all open sessions on this server
            count = await end_all_open_sessions_on_server(
                session, server_db_id, event.timestamp
            )

            logger.info(
                f"Ended {count} session(s) for server {event.server_id} (server stopping)"
            )
