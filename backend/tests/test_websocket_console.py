"""
Tests for the WebSocket console endpoint with docker-py integration.
Tests real-time console functionality with mocked dependencies.
"""
import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.service import get_identity_service, get_system_user
from app.auth.session import AUTH_COOKIE_NAME
from app.main import api_app
from tests.support.runtime import patch_runtime_resource


class MockMCInstance:
    """Mock MCInstance for testing WebSocket console functionality."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self._exists = True
        self._running = True
        self._container_id = "test_container_123"

    async def exists(self):
        """Return whether server exists."""
        return self._exists

    async def running(self):
        """Return whether server is running."""
        return self._running

    async def get_container_id(self):
        """Return the container ID."""
        return self._container_id


class MockDockerAPIClient:
    """Mock Docker API client for testing."""

    def __init__(self):
        self.logs_content = (
            "[10:30:21] [Server thread/INFO]: Starting minecraft server version 1.20.4\n"
            "[10:30:21] [Server thread/INFO]: Loading properties\n"
            "[10:30:22] [RCON Listener #1/INFO]: RCON running on 0.0.0.0:25575\n"
            '[10:30:22] [Server thread/INFO]: Done (1.234s)! For help, type "help"\n'
        )
        self._socket = MockSocket()
        self.resize_calls: list[tuple[str, int, int]] = []
        self.close_calls = 0

    def logs(self, container_id, stdout=True, stderr=True, tail=1000):
        """Mock logs method."""
        _ = container_id, stdout, stderr, tail
        return self.logs_content.encode("utf-8")

    def attach_socket(self, container_id, params=None):
        """Mock attach_socket method."""
        _ = container_id, params
        return self._socket

    def resize(self, container_id, height, width):
        """Mock resize method."""
        self.resize_calls.append((container_id, height, width))

    def close(self):
        self.close_calls += 1


class MockSocket:
    """Mock socket for attach_socket."""

    def __init__(self):
        self._sock = MockRawSocket()
        self.close_calls = 0
        self.reader_finished_before_close = False

    def close(self):
        self.close_calls += 1
        task = self._sock.read_task
        self.reader_finished_before_close = task is not None and task.done()


class MockRawSocket:
    """Mock raw socket with async support."""

    def __init__(self):
        self._blocking = True
        self._closed = False
        self._sent_data: list[bytes] = []
        self.read_task: asyncio.Task | None = None

    def setblocking(self, blocking):
        self._blocking = blocking

    def fileno(self):
        """Return a fake file descriptor."""
        return -1


async def mock_socket_read_loop(self):
    self._socket._sock.read_task = asyncio.current_task()
    await asyncio.Future()


def wait_for_processed_messages(websocket):
    websocket.send_json({"type": "barrier"})
    assert websocket.receive_json() == {"type": "info", "message": "未知消息类型: barrier"}


@pytest.fixture
def mock_instance():
    """Create mock instance."""
    server_id = "test_server"
    instance = MockMCInstance(server_id)
    return server_id, instance


@pytest.fixture
def client(monkeypatch):
    """Create test client."""
    client = TestClient(api_app)
    monkeypatch.setattr(
        get_identity_service(), "get_current_session_user",
        AsyncMock(return_value=get_system_user()),
    )
    token, _ = get_identity_service().create_session_token(get_system_user())
    client.cookies.set(AUTH_COOKIE_NAME, token, path="/")
    return client


def console_url(server_id: str, cols: int = 80, rows: int = 24) -> str:
    return f"/servers/{server_id}/console?cols={cols}&rows={rows}"


@pytest.mark.parametrize("failure", ["history", "input", "resize", "connect", "stream"])
def test_console_adapter_errors_are_safe_and_keep_frame_policy(client, mock_instance, caplog, failure):
    secret = "synthetic-console-adapter-password"
    server_id, instance = mock_instance
    adapter = MockDockerAPIClient()
    with (
        patch_runtime_resource("docker_mc_manager") as manager,
        patch("docker.APIClient", return_value=adapter) as constructor,
        patch("app.websocket.console.ConsoleWebSocketHandler._socket_read_loop", mock_socket_read_loop)
        if failure != "stream" else nullcontext(),
        patch.object(asyncio.SelectorEventLoop, "sock_recv", new_callable=AsyncMock) as receiver,
        patch.object(asyncio.SelectorEventLoop, "sock_sendall", new_callable=AsyncMock) as sender,
    ):
        manager.get_instance.return_value = instance
        if failure == "history":
            adapter.logs = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(secret))
        elif failure == "input":
            sender.side_effect = RuntimeError(secret)
        elif failure == "resize":
            adapter.resize = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(secret))
        elif failure == "connect":
            constructor.side_effect = RuntimeError(secret)
        else:
            receiver.side_effect = RuntimeError(secret)
        with client.websocket_connect(console_url(server_id)) as websocket:
            initial = websocket.receive_json()
            if failure in {"history", "connect"}:
                assert initial["type"] == "error"
                assert secret not in initial["message"]
            else:
                assert initial["type"] == "log"
            if failure == "connect":
                with pytest.raises(WebSocketDisconnect):
                    websocket.receive_json()
            elif failure == "stream":
                error = websocket.receive_json()
                assert error == {"type": "error", "message": "控制台日志连接中断，请重新连接"}
                wait_for_processed_messages(websocket)
            else:
                if failure == "input":
                    websocket.send_json({"type": "input", "data": "list\n"})
                    assert websocket.receive_json() == {"type": "info", "message": "发送输入失败，请重试"}
                wait_for_processed_messages(websocket)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    if failure != "connect":
        assert adapter._socket.close_calls == 1 and adapter.close_calls == 1


class TestWebSocketConsole:
    """Test WebSocket console endpoint functionality."""

    def test_websocket_connection_success(self, client, mock_instance):
        """Test successful WebSocket connection with authentication."""
        server_id, instance = mock_instance

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(console_url(server_id)) as websocket:
                # Should receive initial logs
                data = websocket.receive_json()
                assert data["type"] in ["log", "info"]

                # If it's a log message, verify it contains expected content
                if data["type"] == "log":
                    assert (
                        "Starting minecraft server" in data["content"]
                        or "Loading properties" in data["content"]
                    )

    def test_websocket_connection_invalid_cookie(self, client, mock_instance):
        """Test WebSocket connection with invalid session cookie."""
        server_id, instance = mock_instance
        client.cookies.set(AUTH_COOKIE_NAME, "invalid_session", path="/")

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
        ):
            mock_manager.get_instance.return_value = instance

            with (
                pytest.raises(WebSocketDisconnect),
                client.websocket_connect(console_url(server_id)) as websocket,
            ):
                websocket.receive_json()

    def test_websocket_server_not_found(self, client, mock_instance):
        """Test WebSocket connection when server doesn't exist."""
        server_id, instance = mock_instance
        instance._exists = False

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
        ):
            mock_manager.get_instance.return_value = instance

            with client.websocket_connect(console_url(server_id)) as websocket:
                # Should receive error message
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert (
                    "未找到" in data["message"]
                    or "not found" in data["message"].lower()
                )

    def test_websocket_server_not_running(self, client, mock_instance):
        """Test WebSocket connection when server is not running."""
        server_id, instance = mock_instance
        instance._running = False

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
        ):
            mock_manager.get_instance.return_value = instance

            with client.websocket_connect(console_url(server_id)) as websocket:
                # Should receive error message about server not running
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert (
                    "未运行" in data["message"]
                    or "not running" in data["message"].lower()
                )

    def test_websocket_invalid_message_format(self, client, mock_instance):
        """Test handling of invalid message formats."""
        server_id, instance = mock_instance

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(console_url(server_id)) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send invalid JSON
                websocket.send_text("invalid json")

                # Should receive error message about format
                response = websocket.receive_json()
                assert response["type"] == "info"
                assert (
                    "格式错误" in response["message"]
                    or "format" in response["message"].lower()
                )

    def test_websocket_message_missing_type(self, client, mock_instance):
        """Test handling of messages missing type field."""
        server_id, instance = mock_instance

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(console_url(server_id)) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send message without type
                message_without_type = {"data": "list"}
                websocket.send_json(message_without_type)

                # Should receive error message about missing type
                response = websocket.receive_json()
                assert response["type"] == "info"
                assert "type" in response["message"]

    def test_websocket_empty_input(self, client, mock_instance):
        server_id, instance = mock_instance
        with (
            patch_runtime_resource("docker_mc_manager") as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch("app.websocket.console.ConsoleWebSocketHandler._socket_read_loop", mock_socket_read_loop),
            patch.object(asyncio.SelectorEventLoop, "sock_sendall", new_callable=AsyncMock) as send_input,
        ):
            mock_manager.get_instance.return_value = instance
            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client
            with client.websocket_connect(console_url(server_id)) as websocket:
                assert websocket.receive_json()["type"] == "log"
                websocket.send_json({"type": "input", "data": ""})
                wait_for_processed_messages(websocket)
                send_input.assert_not_awaited()


    def test_websocket_no_session(self, client, mock_instance):
        """Test WebSocket connection without authentication cookie."""
        server_id, _ = mock_instance
        client.cookies.clear()

        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            f"/servers/{server_id}/console?cols=80&rows=24"
        ) as websocket:
            websocket.receive_json()

    def test_websocket_missing_cols_rows(self, client, mock_instance):
        """Test WebSocket connection without required cols/rows parameters."""
        server_id, _ = mock_instance

        # Should fail when cols/rows are missing
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            f"/servers/{server_id}/console"
        ) as websocket:
            websocket.receive_json()

    def test_websocket_connection_lifecycle(self, client, mock_instance):
        server_id, instance = mock_instance
        with (
            patch_runtime_resource("docker_mc_manager") as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch("app.websocket.console.ConsoleWebSocketHandler._socket_read_loop", mock_socket_read_loop),
            patch.object(asyncio.SelectorEventLoop, "sock_sendall", new_callable=AsyncMock) as send_input,
        ):
            mock_manager.get_instance.return_value = instance
            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client
            with client.websocket_connect(console_url(server_id)) as websocket:
                assert websocket.receive_json()["type"] == "log"
                websocket.send_json({"type": "input", "data": "list\n"})
                wait_for_processed_messages(websocket)
                send_input.assert_awaited_once_with(mock_docker_client._socket._sock, b"list\n")
                reader = mock_docker_client._socket._sock.read_task
                assert reader is not None and not reader.done()

            assert reader.done()
            assert mock_docker_client._socket.reader_finished_before_close
            assert mock_docker_client._socket.close_calls == 1
            assert mock_docker_client.close_calls == 1


    def test_websocket_resize_message(self, client, mock_instance):
        server_id, instance = mock_instance
        with (
            patch_runtime_resource("docker_mc_manager") as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch("app.websocket.console.ConsoleWebSocketHandler._socket_read_loop", mock_socket_read_loop),
        ):
            mock_manager.get_instance.return_value = instance
            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client
            with client.websocket_connect(console_url(server_id)) as websocket:
                assert websocket.receive_json()["type"] == "log"
                websocket.send_json({"type": "resize", "width": 120, "height": 40})
                wait_for_processed_messages(websocket)
                assert mock_docker_client.resize_calls == [
                    ("test_container_123", 25, 81),
                    ("test_container_123", 24, 80),
                    ("test_container_123", 40, 120),
                ]


    def test_websocket_resize_invalid_dimensions(self, client, mock_instance):
        server_id, instance = mock_instance
        with (
            patch_runtime_resource("docker_mc_manager") as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch("app.websocket.console.ConsoleWebSocketHandler._socket_read_loop", mock_socket_read_loop),
        ):
            mock_manager.get_instance.return_value = instance
            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client
            with client.websocket_connect(console_url(server_id)) as websocket:
                assert websocket.receive_json()["type"] == "log"
                websocket.send_json({"type": "resize", "width": -1, "height": -1})
                websocket.send_json({"type": "resize", "width": "abc", "height": "def"})
                wait_for_processed_messages(websocket)
                assert mock_docker_client.resize_calls == [
                    ("test_container_123", 25, 81),
                    ("test_container_123", 24, 80),
                ]


    def test_websocket_unknown_message_type(self, client, mock_instance):
        """Test handling of unknown message types."""
        server_id, instance = mock_instance

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(console_url(server_id)) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send unknown message type
                websocket.send_json({"type": "unknown_type", "data": "test"})

                # Should receive info message about unknown type
                response = websocket.receive_json()
                assert response["type"] == "info"
                assert "unknown_type" in response["message"]

    def test_websocket_history_logs_empty(self, client, mock_instance):
        """Test handling when no history logs are available."""
        server_id, instance = mock_instance

        with (
            patch_runtime_resource('docker_mc_manager') as mock_manager,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client.logs_content = ""  # Empty logs
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(console_url(server_id)) as websocket:
                # Should receive info message about no logs
                data = websocket.receive_json()
                assert data["type"] == "info"
                assert "暂无最近日志" in data["content"]


if __name__ == "__main__":
    pytest.main([__file__])
