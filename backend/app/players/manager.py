"""Main player system manager."""

from typing import Optional

from ..config import settings
from ..events import event_dispatcher
from ..events.base import SystemCrashDetectedEvent
from ..log_monitor import LogMonitor, LogParser
from ..logger import log_exception, logger
from ..minecraft import DockerMCManager
from .chat_tracker import ChatTracker
from .heartbeat import HeartbeatManager
from .player_manager import PlayerManager
from .player_syncer import PlayerSyncer
from .session_tracker import SessionTracker
from .skin_fetcher import SkinFetcher
from .skin_updater import PlayerSkinUpdater


class PlayerSystemManager:
    """Main manager for player tracking system."""

    def __init__(self):
        """Initialize player system manager."""
        # Core dependencies
        self.mc_manager = DockerMCManager(settings.server_path)

        # Log parser and monitor (will be initialized in start_monitoring)
        self.log_parser: Optional[LogParser] = None
        self.log_monitor: Optional[LogMonitor] = None

        # Player subsystems
        self.player_manager = PlayerManager(
            event_dispatcher=event_dispatcher,
        )

        self.session_tracker = SessionTracker(
            event_dispatcher=event_dispatcher,
        )

        self.chat_tracker = ChatTracker(
            event_dispatcher=event_dispatcher,
        )

        # Skin management
        self.skin_fetcher = SkinFetcher()
        self.skin_updater = PlayerSkinUpdater(
            skin_fetcher=self.skin_fetcher, event_dispatcher=event_dispatcher
        )

        # System reliability
        self.heartbeat_manager = HeartbeatManager(event_dispatcher=event_dispatcher)
        self.player_syncer = PlayerSyncer(
            mc_manager=self.mc_manager,
            event_dispatcher=event_dispatcher,
        )

        # Register crash event handler
        event_dispatcher.on_system_crash_detected(self._handle_system_crash)

    async def start_monitoring(self) -> None:
        """Start player monitoring system."""
        logger.info("Starting player monitoring system...")

        # Initialize log monitor
        self.log_parser = LogParser()
        self.log_monitor = LogMonitor(
            event_dispatcher=event_dispatcher,
            log_parser=self.log_parser,
        )

        # Start heartbeat (includes crash detection)
        await self.heartbeat_manager.start()

        # Start log monitoring for existing servers
        servers = []
        try:
            servers = await self.mc_manager.get_all_server_names()
        except Exception as e:
            logger.error(
                f"Error starting log monitoring for existing servers: {e}",
                exc_info=True,
            )

        for server_id in servers:
            await self._start_log_monitoring(server_id)

        # Start background tasks
        await self.player_syncer.start()

        logger.info("Player monitoring system started successfully")

    async def stop_monitoring(self) -> None:
        """Stop player monitoring system."""
        logger.info("Stopping player monitoring system...")

        # Stop background tasks
        await self.player_syncer.stop()

        # Stop log monitoring
        if self.log_monitor:
            await self.log_monitor.stop_all()

        # Stop heartbeat
        await self.heartbeat_manager.stop()

        logger.info("Player monitoring system stopped")

    async def _handle_system_crash(self, event: SystemCrashDetectedEvent) -> None:
        """Handle system crash detected event.

        Triggers player sync to sync actual player states.

        Args:
            event: System crash detected event
        """
        logger.info(
            f"System crash event received - triggering player sync "
            f"(crash at {event.crash_timestamp}, {event.time_since_crash:.0f}s ago)"
        )
        # Trigger immediate validation of all servers
        await self.player_syncer._validate_all_servers()

    @log_exception("Error starting log monitoring: ")
    async def _start_log_monitoring(self, server_id: str) -> None:
        """Start log monitoring for a server.

        Args:
            server_id: Server identifier
        """
        instance = self.mc_manager.get_instance(server_id)
        log_path = instance.get_data_path() / "logs" / "latest.log"

        if self.log_monitor:
            await self.log_monitor.watch_server(server_id, log_path)
            logger.info(f"Started log monitoring for server {server_id}")

    async def start_server_monitoring(self, server_id: str) -> None:
        """Start log monitoring for a newly created server.

        Called by the create endpoint after server creation.

        Args:
            server_id: Server identifier
        """
        await self._start_log_monitoring(server_id)

    async def stop_server_monitoring(self, server_id: str) -> None:
        """Stop log monitoring for a removed server.

        Called by the remove endpoint before server removal.

        Args:
            server_id: Server identifier
        """
        if self.log_monitor:
            await self.log_monitor.stop_watching(server_id)
            logger.info(f"Stopped log monitoring for server {server_id}")


# Global player system manager instance
player_system_manager = PlayerSystemManager()
