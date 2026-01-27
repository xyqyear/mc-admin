"""
WebSocket console handler for Minecraft server management.
Handles real-time log streaming and command execution using docker-py APIs.
"""

import asyncio
import json
from typing import Any, Optional

import docker
from fastapi import WebSocket, WebSocketDisconnect

from ..logger import log_exception
from ..minecraft import MCInstance

# Default number of history log lines to fetch
HISTORY_LOG_LINES = 10000


class ConsoleWebSocketHandler:
    """Handler for a single WebSocket console connection to a Minecraft server."""

    def __init__(self, websocket: WebSocket, instance: MCInstance):
        self.websocket = websocket
        self.instance = instance
        self._closed: bool = False
        self._socket: Any = None
        self._read_task: Optional[asyncio.Task] = None
        self._docker_client: Optional[docker.APIClient] = None
        self._container_id: Optional[str] = None

    async def handle_connection(self, server_id: str, cols: int, rows: int):
        """Handle the WebSocket connection lifecycle."""
        try:
            await self.websocket.accept()

            if not await self.instance.exists():
                await self._send_error(f"服务器 '{server_id}' 未找到")
                await self.websocket.close()
                return

            if not await self.instance.running():
                await self._send_error(f"服务器 '{server_id}' 未运行")
                await self.websocket.close()
                return

            await self._initialize_connection(cols, rows)
            await self._handle_messages()
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for server {server_id}")
        except Exception as e:
            await self._handle_connection_error(e)
        finally:
            self._cleanup()

    async def _initialize_connection(self, cols: int, rows: int):
        """Initialize connection with Docker attach socket."""
        self._docker_client = docker.APIClient(base_url="unix://var/run/docker.sock")
        self._container_id = await self.instance.get_container_id()

        await self._send_history_logs(self._container_id)

        self._socket = self._docker_client.attach_socket(
            self._container_id,
            params={
                "stdin": 1,
                "stdout": 1,
                "stderr": 1,
                "stream": 1,
            },
        )
        self._socket._sock.setblocking(False)

        self._read_task = asyncio.create_task(self._socket_read_loop())

        # Initial TTY resize like Docker CLI: send +1 size first, then actual size
        if cols > 0 and rows > 0:
            await self._resize_tty(cols + 1, rows + 1)
            await self._resize_tty(cols, rows)

    async def _send_history_logs(self, container_id: str):
        """Fetch and send history logs from container."""
        assert self._docker_client is not None  # Set in _initialize_connection
        docker_client = self._docker_client  # Capture for lambda
        try:
            # Use run_in_executor since docker-py logs() is blocking
            loop = asyncio.get_running_loop()
            logs_bytes = await loop.run_in_executor(
                None,
                lambda: docker_client.logs(
                    container_id,
                    stdout=True,
                    stderr=True,
                    tail=HISTORY_LOG_LINES,
                ),
            )

            logs_content = logs_bytes.decode("utf-8", errors="replace")

            if logs_content.strip():
                await self._send_dict({"type": "log", "content": logs_content})
            else:
                await self._send_dict({"type": "info", "content": "暂无最近日志"})

        except Exception as e:
            await self._send_error(f"获取历史日志失败: {e}")

    async def _socket_read_loop(self):
        """Read from attach socket and send data immediately for raw I/O."""
        loop = asyncio.get_running_loop()

        while not self._closed:
            try:
                data = await loop.sock_recv(self._socket._sock, 4096)
                if not data:
                    break

                content = data.decode("utf-8", errors="replace")
                await self._send_dict({"type": "log", "content": content})

            except BlockingIOError:
                await asyncio.sleep(0.01)
            except Exception as e:
                if not self._closed:
                    await self._send_error(f"Stream error: {e}")
                break

    async def _handle_messages(self):
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

        if message_type == "input":
            await self._handle_input(data)
        elif message_type == "resize":
            await self._handle_resize(data)
        else:
            await self._send_dict(
                {"type": "info", "message": f"未知消息类型: {message_type}"}
            )

    async def _handle_input(self, data: dict):
        """Send raw input to container via attach socket."""
        raw_data = data.get("data", "")
        if not raw_data:
            return

        if self._socket is None:
            await self._send_dict({"type": "info", "message": "控制台连接未建立"})
            return

        try:
            loop = asyncio.get_running_loop()
            await loop.sock_sendall(
                self._socket._sock, raw_data.encode("utf-8")
            )
        except Exception as e:
            await self._send_dict({"type": "info", "message": f"发送输入失败: {e}"})

    async def _handle_resize(self, data: dict):
        """Resize container TTY to match client terminal size."""
        height = data.get("height")
        width = data.get("width")

        if not isinstance(height, int) or not isinstance(width, int):
            return
        if height <= 0 or width <= 0:
            return

        await self._resize_tty(width, height)

    async def _resize_tty(self, cols: int, rows: int):
        """Send resize request to container TTY."""
        if self._docker_client is None or self._container_id is None:
            return

        try:
            docker_client = self._docker_client
            container_id = self._container_id
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: docker_client.resize(container_id, rows, cols),
            )
        except Exception as e:
            print(f"Failed to resize TTY: {e}")

    async def _send_error(self, message: str):
        """Send error message."""
        await self._send_dict({"type": "error", "message": message})

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

    @log_exception("Failed to send data over WebSocket")
    async def _send_dict(self, data: dict):
        await self.websocket.send_text(json.dumps(data))

    def _cleanup(self):
        """Clean up resources."""
        self._closed = True

        if self._read_task:
            self._read_task.cancel()
            self._read_task = None

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        if self._docker_client:
            try:
                self._docker_client.close()
            except Exception:
                pass
            self._docker_client = None
