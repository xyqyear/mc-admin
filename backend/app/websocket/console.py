"""
WebSocket console handler for Minecraft server management.
Handles real-time log streaming and command execution.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from ..minecraft import MCInstance, MCServerStatus


class LogFileHandler(FileSystemEventHandler):
    """File system event handler for monitoring log file changes."""

    def __init__(self, handler: "ConsoleWebSocketHandler"):
        self.handler = handler

    def on_modified(self, event):
        """Handle file modification events."""
        # Handle both str and bytes types for src_path
        src_path = event.src_path
        if isinstance(src_path, bytes):
            src_path = src_path.decode('utf-8', errors='replace')
        else:
            src_path = str(src_path)
        
        if not event.is_directory and src_path.endswith("latest.log"):
            # asyncio.create_task sometimes fails with "RuntimeError: no running event loop"
            # TODO find a way to reuse the existing event loop instead of creating a new one
            asyncio.run(self._send_new_logs())

    async def _send_new_logs(self):
        """Send new log content to WebSocket client with RCON filtering."""
        try:
            logs = await self.handler.instance.get_logs_from_file(
                self.handler.file_pointer["position"]
            )
            if logs.content.strip():
                # Apply RCON filtering to new content
                content = logs.content
                if self.handler.filter_rcon:
                    content = self.handler.instance.filter_rcon_logs(content)
                
                # Only send if there's content after filtering
                if content.strip():
                    await self.handler.websocket.send_text(
                        json.dumps({"type": "log", "content": content})
                    )
                self.handler.file_pointer["position"] = logs.pointer
        except Exception:
            pass


class ConsoleWebSocketHandler:
    """Handler for a single WebSocket console connection to a Minecraft server."""

    def __init__(self, websocket: WebSocket, instance: MCInstance):
        self.websocket = websocket
        self.instance = instance
        self.file_pointer: Dict[str, Any] = {"position": 0}
        self.observer: Optional[BaseObserver] = None
        self.filter_rcon: bool = True  # Default to filtering RCON logs

    async def handle_connection(self, server_id: str):
        """Handle the WebSocket connection lifecycle."""
        try:
            await self.websocket.accept()

            if not await self.instance.exists():
                await self._send_error(f"Server '{server_id}' not found")
                await self.websocket.close()
                return

            await self._initialize_connection()
            await self._handle_messages(server_id)

        except Exception as e:
            await self._handle_connection_error(e)
        finally:
            self._cleanup()

    async def _initialize_connection(self):
        """Initialize connection with logs and file monitoring."""
        log_path = self.instance._get_log_path()
        await self._send_initial_logs(log_path)
        self.observer = self._setup_file_monitoring(log_path)

    async def _send_initial_logs(self, log_path: Path):
        """Send initial log content with RCON filtering."""
        try:
            if log_path.exists():
                file_size = log_path.stat().st_size
                # Read last 1M characters worth of bytes (approximate)
                start_position = -1024 * 1024 if file_size > 1024 * 1024 else 0
                initial_logs = await self.instance.get_logs_from_file_filtered(
                    start_position, filter_rcon=self.filter_rcon
                )
                if initial_logs.content.strip():
                    await self.websocket.send_text(
                        json.dumps({"type": "log", "content": initial_logs.content})
                    )
                self.file_pointer[
                    "position"
                ] = await self.instance.get_log_file_end_pointer()
        except FileNotFoundError:
            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "info",
                        "message": "Log file not found. Logs will appear when the server starts generating them.",
                    }
                )
            )

    def _setup_file_monitoring(self, log_path: Path) -> BaseObserver:
        """Set up file monitoring."""
        event_handler = LogFileHandler(self)
        observer = Observer()
        log_dir = log_path.parent
        if log_dir.exists():
            observer.schedule(event_handler, str(log_dir), recursive=False)
            observer.start()
        return observer

    async def _handle_messages(self, server_id: str):
        """Handle incoming messages."""
        try:
            while True:
                message = await self.websocket.receive_text()
                await self._process_message(message)
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for server {server_id}")

    async def _process_message(self, message: str):
        """Process a single message."""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "command":
                await self._handle_command(data)
            elif message_type == "set_filter":
                await self._handle_filter_change(data)
            elif message_type == "refresh_logs":
                await self._handle_log_refresh(data)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON format")

    async def _handle_command(self, data: dict):
        """Handle command execution."""
        command = data.get("command", "").strip()
        if not command:
            return

        try:
            status = await self.instance.get_status()
            if status == MCServerStatus.HEALTHY:
                result = await self.instance.send_command_rcon(command)
                await self.websocket.send_text(
                    json.dumps(
                        {"type": "command_result", "command": command, "result": result}
                    )
                )
            else:
                await self._send_error(
                    f"Server must be healthy to send commands (current status: {status})"
                )
        except Exception as e:
            await self._send_error(f"Failed to send command: {str(e)}")

    async def _handle_filter_change(self, data: dict):
        """Handle RCON filter toggle."""
        try:
            filter_rcon = data.get("filter_rcon", True)
            self.filter_rcon = bool(filter_rcon)
            
            # Send confirmation
            await self.websocket.send_text(
                json.dumps({
                    "type": "filter_updated",
                    "filter_rcon": self.filter_rcon
                })
            )
        except Exception as e:
            await self._send_error(f"Failed to update filter: {str(e)}")

    async def _handle_log_refresh(self, _data: dict):
        """Handle log refresh request with current filter settings."""
        try:
            log_path = self.instance._get_log_path()
            
            if not log_path.exists():
                await self.websocket.send_text(
                    json.dumps({
                        "type": "info",
                        "message": "Log file not found. Logs will appear when the server starts generating them.",
                    })
                )
                return
            
            # Get fresh logs with current filter settings
            file_size = log_path.stat().st_size
            # Read last 1M characters worth of bytes (approximate)
            start_position = -1024 * 1024 if file_size > 1024 * 1024 else 0
            fresh_logs = await self.instance.get_logs_from_file_filtered(
                start_position, filter_rcon=self.filter_rcon
            )
            
            # Send fresh logs
            if fresh_logs.content.strip():
                await self.websocket.send_text(
                    json.dumps({
                        "type": "logs_refreshed", 
                        "content": fresh_logs.content
                    })
                )
            else:
                await self.websocket.send_text(
                    json.dumps({
                        "type": "logs_refreshed", 
                        "content": ""
                    })
                )
                
            # Update file pointer to current end
            self.file_pointer["position"] = await self.instance.get_log_file_end_pointer()
            
        except Exception as e:
            await self._send_error(f"Failed to refresh logs: {str(e)}")

    async def _send_error(self, message: str):
        """Send error message."""
        try:
            await self.websocket.send_text(
                json.dumps({"type": "error", "message": message})
            )
        except Exception:
            pass

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

    def _cleanup(self):
        """Clean up resources."""
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
