"""Main player system manager."""

from typing import Optional

from ..config import settings
from ..events import event_dispatcher
from ..log_monitor import LogMonitor, LogParser
from ..logger import logger
from ..minecraft import DockerMCManager
from ..server_tracker import ServerTracker
from .chat_tracker import ChatTracker
from .heartbeat import HeartbeatManager
from .player_manager import PlayerManager
from .rcon_validator import RCONValidator
from .session_tracker import SessionTracker
from .skin_fetcher import SkinFetcher
from .skin_updater import PlayerSkinUpdater


class PlayerSystemManager:
    """Main manager for player tracking system."""

    def __init__(self):
        """Initialize player system manager."""
        # Core dependencies
        self.mc_manager = DockerMCManager(settings.server_path)

        # Server tracker
        self.server_tracker = ServerTracker(
            mc_manager=self.mc_manager,
            event_dispatcher=event_dispatcher,
        )

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
        self.rcon_validator = RCONValidator(
            mc_manager=self.mc_manager,
            server_tracker=self.server_tracker,
            event_dispatcher=event_dispatcher,
        )

        # Register crash event handler
        event_dispatcher.on_system_crash_detected(self._handle_system_crash)

    async def start_monitoring(self) -> None:
        """Start player monitoring system."""
        logger.info("Starting player monitoring system...")

        # Initialize log parser (reads config dynamically for real-time updates)
        try:
            self.log_parser = LogParser()
            logger.info(
                "Log parser initialized with dynamic configuration (real-time updates enabled)"
            )
        except Exception as e:
            logger.error(
                f"Failed to initialize log parser from config: {e}", exc_info=True
            )
            raise

        # Initialize log monitor
        self.log_monitor = LogMonitor(
            event_dispatcher=event_dispatcher,
            log_parser=self.log_parser,
        )

        # Start server tracker
        await self.server_tracker.start_tracking()

        # Start heartbeat (includes crash detection)
        await self.heartbeat_manager.start()

        # Register handlers for server lifecycle events
        event_dispatcher.on_server_created(self._on_server_created)
        event_dispatcher.on_server_removed(self._on_server_removed)

        # Start log monitoring for existing servers
        try:
            servers = await self.mc_manager.get_all_server_names()
            for server_id in servers:
                await self._start_log_monitoring(server_id)
        except Exception as e:
            logger.error(
                f"Error starting log monitoring for existing servers: {e}",
                exc_info=True,
            )

        # Start background tasks
        await self.rcon_validator.start()

        logger.info("Player monitoring system started successfully")

    async def stop_monitoring(self) -> None:
        """Stop player monitoring system."""
        logger.info("Stopping player monitoring system...")

        # Stop background tasks
        await self.rcon_validator.stop()

        # Stop log monitoring
        if self.log_monitor:
            await self.log_monitor.stop_all()

        # Stop heartbeat
        await self.heartbeat_manager.stop()

        # Stop server tracker
        await self.server_tracker.stop_tracking()

        logger.info("Player monitoring system stopped")

    async def _on_server_created(self, event) -> None:
        """Handle server created event.

        Args:
            event: Server created event
        """
        logger.info(f"Server created event received: {event.server_id}")
        await self._start_log_monitoring(event.server_id)

    async def _on_server_removed(self, event) -> None:
        """Handle server removed event.

        Args:
            event: Server removed event
        """
        logger.info(f"Server removed event received: {event.server_id}")
        if self.log_monitor:
            await self.log_monitor.stop_watching(event.server_id)

    async def _handle_system_crash(self, event) -> None:
        """Handle system crash detected event.

        Triggers RCON validation to sync actual player states.

        Args:
            event: System crash detected event
        """
        logger.info(
            f"System crash event received - triggering RCON validation "
            f"(crash at {event.crash_timestamp}, {event.time_since_crash:.0f}s ago)"
        )
        # Trigger immediate validation of all servers
        await self.rcon_validator._validate_all_servers()

    async def _start_log_monitoring(self, server_id: str) -> None:
        """Start log monitoring for a server.

        Args:
            server_id: Server identifier
        """
        try:
            instance = self.mc_manager.get_instance(server_id)
            log_path = instance.get_data_path() / "logs" / "latest.log"

            if self.log_monitor:
                await self.log_monitor.watch_server(server_id, log_path)
                logger.info(f"Started log monitoring for server {server_id}")
        except Exception as e:
            logger.error(
                f"Error starting log monitoring for {server_id}: {e}", exc_info=True
            )


# Global player system manager instance
player_system_manager = PlayerSystemManager()
