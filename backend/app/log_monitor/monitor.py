"""Log file monitoring using watchfiles."""

import asyncio
from pathlib import Path
from typing import Dict

import aiofiles
from aiofiles import os as aioos
from watchfiles import Change, awatch

from ..events.base import (
    BaseEvent,
    PlayerAchievementEvent,
    PlayerChatMessageEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from ..events.dispatcher import EventDispatcher
from ..logger import logger
from .parser import LogParser


class LogMonitor:
    """Monitors Minecraft server log files and emits events."""

    def __init__(self, event_dispatcher: EventDispatcher, log_parser: LogParser):
        """Initialize log monitor.

        Args:
            event_dispatcher: Event dispatcher for emitting events
            log_parser: Log parser for parsing log lines
        """
        self.event_dispatcher = event_dispatcher
        self.log_parser = log_parser

        # Track file pointers for each server
        self._file_pointers: Dict[str, int] = {}

        # Track watch tasks for each server
        self._watch_tasks: Dict[str, asyncio.Task] = {}

        # Flag to stop all watches
        self._stop_flag = False

    async def watch_server(self, server_id: str, log_path: Path) -> None:
        """Start watching a server's log file.

        Args:
            server_id: Server identifier
            log_path: Path to the log file (typically logs/latest.log)
        """
        if server_id in self._watch_tasks:
            logger.warning(f"Already watching logs for server {server_id}")
            return

        # Create watch task
        task = asyncio.create_task(self._watch_loop(server_id, log_path))
        self._watch_tasks[server_id] = task
        logger.info(f"Started watching logs for server {server_id}")

    async def stop_watching(self, server_id: str) -> None:
        """Stop watching a server's log file.

        Args:
            server_id: Server identifier
        """
        if server_id not in self._watch_tasks:
            logger.warning(f"Not watching logs for server {server_id}")
            return

        # Cancel watch task
        task = self._watch_tasks.pop(server_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Remove file pointer
        self._file_pointers.pop(server_id, None)

        logger.info(f"Stopped watching logs for server {server_id}")

    async def stop_all(self) -> None:
        """Stop watching all servers."""
        self._stop_flag = True

        # Cancel all watch tasks
        for server_id in list(self._watch_tasks.keys()):
            await self.stop_watching(server_id)

        logger.info("Stopped all log monitoring")

    async def _watch_loop(self, server_id: str, log_path: Path) -> None:
        """Watch loop for a single server log file.

        Args:
            server_id: Server identifier
            log_path: Path to log file
        """
        # Initialize file pointer
        if await aioos.path.exists(log_path):
            # Start from current end of file
            self._file_pointers[server_id] = await aioos.path.getsize(log_path)
            logger.info(
                f"Log file found for {server_id}, size: {self._file_pointers[server_id]}"
            )
        else:
            self._file_pointers[server_id] = 0
            logger.info(
                f"Log file not found for {server_id}, will start from beginning when created"
            )

        # wait for the log file to be created
        while not await aioos.path.exists(log_path):
            if self._stop_flag:
                return
            await asyncio.sleep(1)

        try:
            async for changes in awatch(log_path.parent, stop_event=None):
                if self._stop_flag:
                    break

                for change_type, changed_path in changes:
                    if changed_path != str(log_path):
                        continue

                    if change_type == Change.deleted:
                        logger.info(f"Log file deleted for {server_id}")
                        continue

                    if change_type == Change.added:
                        logger.info(f"Log file created for {server_id}")
                        self._file_pointers[server_id] = 0
                    logger.debug(f"Processing log changes for {server_id}")
                    await self._process_log_changes(server_id, log_path)

        except asyncio.CancelledError:
            logger.debug(f"Watch loop cancelled for {server_id}")
            raise
        except Exception as e:
            logger.error(f"Error in watch loop for {server_id}: {e}", exc_info=True)

    async def _process_log_changes(self, server_id: str, log_path: Path) -> None:
        """Process changes to a log file.

        Args:
            server_id: Server identifier
            log_path: Path to log file
        """
        try:
            if not await aioos.path.exists(log_path):
                return

            current_size = await aioos.path.getsize(log_path)
            last_position = self._file_pointers.get(server_id, 0)

            # Check if file was truncated (log rotation)
            if current_size < last_position:
                logger.info(
                    f"Log file truncated for {server_id}, reading from beginning"
                )
                last_position = 0

            # Read new content
            if current_size > last_position:
                async with aiofiles.open(
                    log_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    await f.seek(last_position)
                    new_content = await f.read()
                    read_position = await f.tell()

                # Update file pointer
                self._file_pointers[server_id] = read_position

                # Process new lines
                lines = new_content.splitlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Parse line and emit event
                    event = self.log_parser.parse_line(server_id, line)
                    if event:
                        await self._dispatch_event(event)

        except Exception as e:
            logger.error(
                f"Error processing log changes for {server_id}: {e}", exc_info=True
            )

    async def _dispatch_event(self, event) -> None:
        """Dispatch an event through the event dispatcher.

        Args:
            event: Event to dispatch
        """
        try:
            # Use match syntax to dispatch based on event type
            match event:
                case event if isinstance(event, BaseEvent):
                    # Match by event class type for better type safety
                    match event:
                        case PlayerUuidDiscoveredEvent():
                            await self.event_dispatcher.dispatch_player_uuid_discovered(
                                event
                            )
                        case PlayerJoinedEvent():
                            await self.event_dispatcher.dispatch_player_joined(event)
                        case PlayerLeftEvent():
                            await self.event_dispatcher.dispatch_player_left(event)
                        case PlayerChatMessageEvent():
                            await self.event_dispatcher.dispatch_player_chat_message(
                                event
                            )
                        case PlayerAchievementEvent():
                            await self.event_dispatcher.dispatch_player_achievement(
                                event
                            )
                        case ServerStoppingEvent():
                            await self.event_dispatcher.dispatch_server_stopping(event)
                        case _:
                            logger.warning(
                                f"Unhandled event type: {type(event).__name__}"
                            )
                case _:
                    logger.warning(f"Invalid event object: {event}")
        except Exception as e:
            logger.error(
                f"Error dispatching event {type(event).__name__}: {e}", exc_info=True
            )
