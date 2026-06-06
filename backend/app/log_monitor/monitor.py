"""Log file monitoring using watchfiles."""

import asyncio
from pathlib import Path
from typing import Dict

import aiofiles
from aiofiles import os as aioos
from watchfiles import Change, awatch

from ..db.database import get_async_session
from ..logger import logger
from ..minecraft import docker_mc_manager
from ..players.crud import upsert_player
from ..players.tracking import (
    close_server_sessions,
    process_player_join,
    process_player_left,
    record_achievement,
    record_chat_message,
)
from .events import (
    LogEvent,
    PlayerAchievementEvent,
    PlayerChatMessageEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from .parser import LogParser


class LogMonitor:
    """Monitors Minecraft server log files and dispatches tracking actions."""

    def __init__(self):
        self.log_parser = LogParser()

        # Track file pointers for each server
        self._file_pointers: Dict[str, int] = {}

        # Track watch tasks for each server
        self._watch_tasks: Dict[str, asyncio.Task] = {}

        # Flag to stop all watches
        self._stop_flag = False

    async def start_server(self, server_id: str) -> None:
        """Start watching a server's log file.

        Resolves the log path from the server's data directory.
        """
        instance = docker_mc_manager.get_instance(server_id)
        log_path = instance.get_data_path() / "logs" / "latest.log"
        await self._watch_server(server_id, log_path)
        logger.info(f"Started log monitoring for server {server_id}")

    async def _watch_server(self, server_id: str, log_path: Path) -> None:
        """Start watching a server's log file at the given path."""
        if server_id in self._watch_tasks:
            logger.warning(f"Already watching logs for server {server_id}")
            return

        task = asyncio.create_task(self._watch_loop(server_id, log_path))
        self._watch_tasks[server_id] = task
        logger.info(f"Started watching logs for server {server_id}")

    async def stop_watching(self, server_id: str) -> None:
        """Stop watching a server's log file."""
        if server_id not in self._watch_tasks:
            logger.warning(f"Not watching logs for server {server_id}")
            return

        task = self._watch_tasks.pop(server_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        self._file_pointers.pop(server_id, None)
        logger.info(f"Stopped watching logs for server {server_id}")

    def is_watching(self, server_id: str) -> bool:
        task = self._watch_tasks.get(server_id)
        return task is not None and not task.done()

    async def stop_all(self) -> None:
        """Stop watching all servers."""
        self._stop_flag = True

        for server_id in list(self._watch_tasks.keys()):
            await self.stop_watching(server_id)

        logger.info("Stopped all log monitoring")

    async def _watch_loop(self, server_id: str, log_path: Path) -> None:
        """Watch loop for a single server log file."""
        # Initialize file pointer
        if await aioos.path.exists(log_path):
            self._file_pointers[server_id] = await aioos.path.getsize(log_path)
            logger.info(
                f"Log file found for {server_id}, size: {self._file_pointers[server_id]}"
            )
        else:
            self._file_pointers[server_id] = 0
            logger.info(
                f"Log file not found for {server_id}, will start from beginning when created"
            )

        # Wait for the log file to be created
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
        """Process changes to a log file."""
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

                self._file_pointers[server_id] = read_position

                lines = new_content.splitlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    event = self.log_parser.parse_line(server_id, line)
                    if event:
                        await self._handle_event(event)

        except Exception as e:
            logger.error(
                f"Error processing log changes for {server_id}: {e}", exc_info=True
            )

    async def _handle_event(self, event: LogEvent) -> None:
        """Route a parsed log event to the appropriate tracking function."""
        try:
            match event:
                case PlayerUuidDiscoveredEvent():
                    async with get_async_session() as session:
                        updated = await upsert_player(
                            session, event.uuid, event.player_name
                        )
                    if updated:
                        logger.info(
                            f"Updated player UUID: {event.player_name} = {event.uuid}"
                        )
                case PlayerJoinedEvent():
                    await process_player_join(
                        event.server_id, event.player_name, event.timestamp
                    )
                case PlayerLeftEvent():
                    await process_player_left(
                        event.server_id,
                        event.player_name,
                        event.reason,
                        event.timestamp,
                    )
                case PlayerChatMessageEvent():
                    await record_chat_message(
                        event.server_id,
                        event.player_name,
                        event.message,
                        event.timestamp,
                    )
                case PlayerAchievementEvent():
                    await record_achievement(
                        event.server_id,
                        event.player_name,
                        event.achievement_name,
                        event.timestamp,
                    )
                case ServerStoppingEvent():
                    await close_server_sessions(event.server_id, event.timestamp)
                case _:
                    logger.warning(f"Unhandled event type: {type(event).__name__}")
        except Exception as e:
            logger.error(
                f"Error handling event {type(event).__name__}: {e}", exc_info=True
            )


log_monitor = LogMonitor()
