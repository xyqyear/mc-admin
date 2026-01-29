"""
Tests for the WebSocket console endpoint with docker-py integration.
Tests real-time console functionality with mocked dependencies.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app


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
        """Mock close method."""
        pass


class MockSocket:
    """Mock socket for attach_socket."""

    def __init__(self):
        self._sock = MockRawSocket()

    def close(self):
        pass


class MockRawSocket:
    """Mock raw socket with async support."""

    def __init__(self):
        self._blocking = True
        self._closed = False
        self._sent_data: list[bytes] = []

    def setblocking(self, blocking):
        self._blocking = blocking

    def fileno(self):
        """Return a fake file descriptor."""
        return -1


async def mock_socket_read_loop(self):
    """Mock socket read loop that does nothing (prevents blocking)."""
    import asyncio

    while not self._closed:
        await asyncio.sleep(0.1)


@pytest.fixture
def mock_instance():
    """Create mock instance."""
    server_id = "test_server"
    instance = MockMCInstance(server_id)
    return server_id, instance


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(api_app)


class TestWebSocketConsole:
    """Test WebSocket console endpoint functionality."""

    def test_websocket_connection_success(self, client, mock_instance):
        """Test successful WebSocket connection with authentication."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
                # Should receive initial logs
                data = websocket.receive_json()
                assert data["type"] in ["log", "info"]

                # If it's a log message, verify it contains expected content
                if data["type"] == "log":
                    assert (
                        "Starting minecraft server" in data["content"]
                        or "Loading properties" in data["content"]
                    )

    def test_websocket_connection_invalid_token(self, client, mock_instance):
        """Test WebSocket connection with invalid token."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            # This should fail due to invalid token
            with pytest.raises(Exception):
                with client.websocket_connect(
                    f"/servers/{server_id}/console?token=invalid_token&cols=80&rows=24"
                ) as websocket:
                    websocket.receive_json()

    def test_websocket_server_not_found(self, client, mock_instance):
        """Test WebSocket connection when server doesn't exist."""
        server_id, instance = mock_instance
        instance._exists = False

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
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
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
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
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
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
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
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
        """Test handling of empty input data."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send empty input - should be silently ignored
                empty_input = {"type": "input", "data": ""}
                websocket.send_json(empty_input)

                # Connection should remain stable (no error response expected)
                # The test passes if no exception is raised

    def test_websocket_no_token(self, client, mock_instance):
        """Test WebSocket connection without authentication token."""
        server_id, _ = mock_instance

        # Should fail when no token is provided (missing required params)
        with pytest.raises(Exception):
            with client.websocket_connect(
                f"/servers/{server_id}/console?cols=80&rows=24"
            ) as websocket:
                websocket.receive_json()

    def test_websocket_missing_cols_rows(self, client, mock_instance):
        """Test WebSocket connection without required cols/rows parameters."""
        server_id, _ = mock_instance

        # Should fail when cols/rows are missing
        with pytest.raises(Exception):
            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                websocket.receive_json()

    def test_websocket_connection_lifecycle(self, client, mock_instance):
        """Test the complete WebSocket connection lifecycle."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
                # 1. Receive initial logs first
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # 2. Send raw input (new format)
                websocket.send_json({"type": "input", "data": "list\n"})

                # 3. Connection should close cleanly when exiting context manager

    def test_websocket_resize_message(self, client, mock_instance):
        """Test handling of resize messages."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send resize message
                websocket.send_json({"type": "resize", "width": 120, "height": 40})

                # Connection should remain stable
                # The test passes if no exception is raised

    def test_websocket_resize_invalid_dimensions(self, client, mock_instance):
        """Test handling of resize messages with invalid dimensions."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send resize with invalid dimensions (negative)
                websocket.send_json({"type": "resize", "width": -1, "height": -1})

                # Send resize with wrong type
                websocket.send_json({"type": "resize", "width": "abc", "height": "def"})

                # Connection should remain stable (invalid resize should be ignored)

    def test_websocket_unknown_message_type(self, client, mock_instance):
        """Test handling of unknown message types."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
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
            patch("app.routers.servers.console.docker_mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
            patch("docker.APIClient") as mock_docker_client_class,
            patch(
                "app.websocket.console.ConsoleWebSocketHandler._socket_read_loop",
                mock_socket_read_loop,
            ),
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            mock_docker_client = MockDockerAPIClient()
            mock_docker_client.logs_content = ""  # Empty logs
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&cols=80&rows=24"
            ) as websocket:
                # Should receive info message about no logs
                data = websocket.receive_json()
                assert data["type"] == "info"
                assert "暂无最近日志" in data["content"]


if __name__ == "__main__":
    pytest.main([__file__])
