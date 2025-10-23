"""Server tracker for monitoring server lifecycle."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from ..db.database import get_async_session
from ..events.base import ServerCreatedEvent, ServerRemovedEvent
from ..events.dispatcher import EventDispatcher
from ..logger import log_exception, logger
from ..minecraft import DockerMCManager
from .crud import (
    create_server,
    get_active_servers,
    get_server_db_id,
    mark_server_removed,
)


class ServerTracker:
    """Tracks server instances and their lifecycle."""

    def __init__(
        self,
        mc_manager: DockerMCManager,
        event_dispatcher: EventDispatcher,
        sync_interval: float = 30,
    ):
        """Initialize server tracker.

        Args:
            mc_manager: Minecraft Docker manager
            event_dispatcher: Event dispatcher for emitting events
            sync_interval: Interval in seconds for server status sync (default: 30)
        """
        self.mc_manager = mc_manager
        self.event_dispatcher = event_dispatcher
        self.sync_interval = sync_interval

        # Tracking state
        self._sync_task: Optional[asyncio.Task] = None
        self._stop_flag = False

    async def start_tracking(self) -> None:
        """Start tracking servers."""
        logger.info("Starting server tracker...")

        # Start sync loop
        self._stop_flag = False
        self._sync_task = asyncio.create_task(self._sync_loop())

        logger.info("Server tracker started")

    async def stop_tracking(self) -> None:
        """Stop tracking servers."""
        logger.info("Stopping server tracker...")

        self._stop_flag = True

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        logger.info("Server tracker stopped")

    async def get_server_db_id(self, server_id: str) -> Optional[int]:
        """Get database ID for a server.

        Args:
            server_id: Server identifier

        Returns:
            Database ID or None if not found
        """
        async with get_async_session() as session:
            return await get_server_db_id(session, server_id)

    async def _sync_loop(self) -> None:
        """Sync loop for monitoring server status."""
        while not self._stop_flag:
            await self._sync_servers()
            await asyncio.sleep(self.sync_interval)

    @log_exception("Error syncing servers: ")
    async def _sync_servers(self) -> None:
        """Sync servers with Docker manager."""
        # Get current servers from file system
        current_servers = set(await self.mc_manager.get_all_server_names())

        # Get servers from database
        async with get_async_session() as session:
            db_servers = await get_active_servers(session)
            db_server_ids = {server.server_id for server in db_servers}

        # Detect new servers (in file system but not in database)
        new_servers = current_servers - db_server_ids
        for server_id in new_servers:
            await self._handle_server_created(server_id)

        # Detect removed servers (in database but not in file system)
        removed_servers = db_server_ids - current_servers
        for server_id in removed_servers:
            await self._handle_server_removed(server_id)

    @log_exception("Error handling server creation: ")
    async def _handle_server_created(self, server_id: str) -> None:
        """Handle server creation.

        Args:
            server_id: Server identifier
        """
        async with get_async_session() as session:
            # Create server record in database
            server = await create_server(session, server_id, datetime.now(timezone.utc))

            logger.info(f"Server created: {server_id} (db_id={server.id})")

            # Emit event
            await self.event_dispatcher.dispatch_server_created(
                ServerCreatedEvent(server_id=server_id)
            )

    @log_exception("Error handling server removal: ")
    async def _handle_server_removed(self, server_id: str) -> None:
        """Handle server removal.

        Args:
            server_id: Server identifier
        """
        async with get_async_session() as session:
            # Mark server as removed in database
            await mark_server_removed(session, server_id, datetime.now(timezone.utc))

            logger.info(f"Server removed: {server_id}")

            # Emit event
            await self.event_dispatcher.dispatch_server_removed(
                ServerRemovedEvent(server_id=server_id)
            )
