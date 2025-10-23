"""Player skin update handler."""

from datetime import datetime, timezone
from typing import Optional

from app.events.dispatcher import EventDispatcher

from ..db.database import get_async_session
from ..logger import log_exception, logger
from .crud import update_player_skin
from .skin_fetcher import SkinFetcher


class PlayerSkinUpdater:
    """Handles player skin updates via event system."""

    def __init__(
        self,
        skin_fetcher: SkinFetcher,
        event_dispatcher: Optional[EventDispatcher] = None,
    ):
        """Initialize skin update handler.

        Args:
            skin_fetcher: Skin fetcher instance
            event_dispatcher: Optional event dispatcher for skin update events
        """
        self.skin_fetcher = skin_fetcher

        # Register event handler if dispatcher provided
        if event_dispatcher:
            event_dispatcher.on_player_skin_update_requested(
                self._handle_skin_update_requested
            )

    @log_exception("Error handling skin update request: ")
    async def _handle_skin_update_requested(self, event) -> None:
        """Handle PlayerSkinUpdateRequestedEvent.

        Args:
            event: PlayerSkinUpdateRequestedEvent with player info
        """
        logger.debug(f"Updating skin for player {event.player_name} ({event.uuid})")

        result = await self.skin_fetcher.fetch_player_skin(event.uuid)

        # Update database with fetched skin
        async with get_async_session() as session:
            now = datetime.now(timezone.utc)
            if result:
                skin_data, avatar_data = result

                await update_player_skin(
                    session, event.player_db_id, skin_data, avatar_data, now
                )

                logger.info(f"Updated skin for player {event.player_name}")
            else:
                logger.warning(f"Failed to fetch skin for player {event.player_name}")
