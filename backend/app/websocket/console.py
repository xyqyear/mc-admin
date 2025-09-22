"""
WebSocket console handler for Minecraft server management.
Handles real-time log streaming and command execution.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import aiofiles.os as aioos
from fastapi import WebSocket, WebSocketDisconnect
from watchfiles import Change, awatch

from ..minecraft import MCInstance


class ConsoleWebSocketHandler:
    """Handler for a single WebSocket console connection to a Minecraft server."""

    def __init__(self, websocket: WebSocket, instance: MCInstance):
        self.websocket = websocket
        self.instance = instance
        self.file_pointer: int = 0
        self.watchfiles_stop_event: Optional[asyncio.Event] = None
        self.filter_rcon: bool = True  # Default to filtering RCON logs
        self.loop = asyncio.get_event_loop()
        self.file_watch_task: Optional[asyncio.Task] = None
        self.file_size_watch_task: Optional[asyncio.Task] = None

    async def handle_connection(self, server_id: str):
        """Handle the WebSocket connection lifecycle."""
        try:
            await self.websocket.accept()

            if not await self.instance.exists():
                await self._send_error(f"服务器 '{server_id}' 未找到")
                await self.websocket.close()
                return

            await self._initialize_connection()
            await self._handle_messages(server_id)
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for server {server_id}")
        except Exception as e:
            await self._handle_connection_error(e)
        finally:
            self._cleanup()

    async def _initialize_connection(self):
        """Initialize connection with logs and file monitoring."""
        log_path = await self.instance._get_log_path()
        await self._send_initial_logs(log_path)
        self.watchfiles_stop_event = asyncio.Event()
        self.file_watch_task = asyncio.create_task(self._watch_log_file(log_path))
        self.file_size_watch_task = asyncio.create_task(
            self._watch_log_file_size(log_path)
        )

    async def _watch_log_file(self, log_path: Path):
        """Watch log file for changes using awatch."""
        log_dir = log_path.parent

        async for changes in awatch(log_dir, stop_event=self.watchfiles_stop_event):
            for change_type, file_path in changes:
                if file_path == str(log_path) and change_type == Change.modified:
                    await self._send_new_logs()
                if file_path == str(log_dir) and change_type == Change.deleted:
                    await self._send_not_found()

    async def _watch_log_file_size(self, log_path: Path):
        """Watch log file size periodically as a fallback."""
        while True:
            await asyncio.sleep(1)
            if not await aioos.path.exists(log_path):
                await self._send_not_found()
            current_size = (await aioos.stat(log_path)).st_size
            if current_size < self.file_pointer:
                # File was truncated or rotated
                self.file_pointer = 0
                await self._send_new_logs()
            elif current_size > self.file_pointer:
                await self._send_new_logs()

    async def _send_logs_with_message_type(
        self,
        log_path: Path,
        message_type: str,
        read_limit: int = 10 * 1024 * 1024,
        return_limit: int = 1024 * 1024,
    ):
        """Send log content with RCON filtering and specified message type."""
        if not await aioos.path.exists(log_path):
            await self._send_not_found()
            return
        try:
            file_size = (await aioos.stat(log_path)).st_size
            start_position = -read_limit if file_size > read_limit else 0
            logs = await self.instance.get_logs_from_file_filtered(
                start_position, filter_rcon=self.filter_rcon, max_chars=return_limit
            )

            if logs.content.strip():
                await self._send_dict({"type": message_type, "content": logs.content})
            else:
                await self._send_dict({"type": "info", "content": "暂无最近日志"})
            self.file_pointer = logs.pointer

        except FileNotFoundError:
            await self._send_not_found()

    async def _send_initial_logs(self, log_path: Path):
        """Send initial log content with RCON filtering."""
        await self._send_logs_with_message_type(log_path, "log")

    async def _send_new_logs(self):
        """Send new log content to WebSocket client with RCON filtering."""
        try:
            logs = await self.instance.get_logs_from_file(self.file_pointer)
            if logs.content.strip():
                # Apply RCON filtering to new content
                content = logs.content
                if self.filter_rcon:
                    content = self.instance.filter_rcon_logs(content)

                # Only send if there's content after filtering
                if content.strip():
                    await self._send_dict({"type": "log", "content": content})

                self.file_pointer = logs.pointer
        except Exception:
            pass

    async def _handle_messages(self, server_id: str):
        """Handle incoming messages."""
        while True:
            message = await self.websocket.receive_text()
            await self._process_message(message)

    async def _process_message(self, message: str):
        """Process a single message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await self._send_dict({"type": "info", "message": "消息格式错误"})
            return

        if not data.get("type"):
            await self._send_dict({"type": "info", "message": "消息中缺少type"})
            return

        message_type = data.get("type")

        if message_type == "command":
            await self._handle_command(data)
        elif message_type == "set_filter":
            await self._handle_filter_change(data)
        elif message_type == "refresh_logs":
            await self._handle_log_refresh(data)

    async def _handle_command(self, data: dict):
        """Handle command execution."""
        command = data.get("command", "").strip()
        if not command:
            return

        try:
            await self.instance.send_command_stdin(command)
        except RuntimeError as e:
            error_message = str(e)
            if "CREATE_CONSOLE_IN_PIPE" in error_message:
                await self._send_dict(
                    {
                        "type": "info",
                        "message": "发送指令需要在Compose文件中设置环境变量CREATE_CONSOLE_IN_PIPE=true",
                    }
                )
            else:
                await self._send_dict({"type": "info", "message": error_message})
        except Exception as e:
            await self._send_dict({"type": "info", "message": str(e)})

    async def _handle_filter_change(self, data: dict):
        """Handle RCON filter toggle."""
        filter_rcon = data.get("filter_rcon", True)
        self.filter_rcon = bool(filter_rcon)

        # Send confirmation message
        await self._send_dict(
            {"type": "filter_updated", "filter_rcon": self.filter_rcon}
        )

    async def _handle_log_refresh(self, _data: dict):
        """Handle log refresh request with current filter settings."""
        log_path = await self.instance._get_log_path()
        await self._send_logs_with_message_type(log_path, "logs_refreshed")

    async def _send_error(self, message: str):
        """Send error message."""
        await self._send_dict({"type": "error", "message": message})

    async def _send_not_found(self):
        """Send not found message."""
        await self._send_error("控制台日志未找到")

    async def _handle_connection_error(self, error: Exception):
        """Handle connection errors."""
        try:
            await self._send_error(f"Connection error: {str(error)}")
        except Exception:
            pass
        finally:
            try:
                await self.websocket.close()
            except Exception:
                pass

    async def _send_dict(self, data: dict):
        try:
            await self.websocket.send_text(json.dumps(data))
        except Exception:
            pass

    def _cleanup(self):
        """Clean up resources."""
        if self.watchfiles_stop_event:
            self.watchfiles_stop_event.set()
        if self.file_watch_task:
            self.file_watch_task.cancel()
        if self.file_size_watch_task:
            self.file_size_watch_task.cancel()
