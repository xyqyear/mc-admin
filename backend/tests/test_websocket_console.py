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

    def logs(self, container_id, stdout=True, stderr=True, tail=1000):
        """Mock logs method."""
        _ = container_id, stdout, stderr, tail
        return self.logs_content.encode("utf-8")

    def attach_socket(self, container_id, params=None):
        """Mock attach_socket method."""
        _ = container_id, params
        return self._socket

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
                f"/servers/{server_id}/console?token=test_master_token"
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
                    f"/servers/{server_id}/console?token=invalid_token"
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
                f"/servers/{server_id}/console?token=test_master_token"
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
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Should receive error message about server not running
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert (
                    "未运行" in data["message"]
                    or "not running" in data["message"].lower()
                )

    def test_websocket_filter_via_url_param(self, client, mock_instance):
        """Test RCON filter is passed via URL parameter."""
        server_id, instance = mock_instance

        # Set up logs with RCON content
        rcon_logs = (
            "[10:30:21] [Server thread/INFO]: Starting minecraft server version 1.20.4\n"
            "[10:30:22] [RCON Listener #1/INFO]: RCON running on 0.0.0.0:25575\n"
            '[10:30:23] [Server thread/INFO]: Done (1.234s)! For help, type "help"\n'
        )

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
            mock_docker_client.logs_content = rcon_logs
            mock_docker_client_class.return_value = mock_docker_client

            # Test with filter_rcon=false - should include RCON lines
            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token&filter_rcon=false"
            ) as websocket:
                initial_data = websocket.receive_json()
                if initial_data["type"] == "log":
                    # RCON lines should NOT be filtered when filter_rcon=false
                    assert "RCON" in initial_data["content"]

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
                f"/servers/{server_id}/console?token=test_master_token"
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
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send message without type
                message_without_type = {"command": "list"}
                websocket.send_json(message_without_type)

                # Should receive error message about missing type
                response = websocket.receive_json()
                assert response["type"] == "info"
                assert "type" in response["message"]

    def test_websocket_empty_command(self, client, mock_instance):
        """Test handling of empty commands."""
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
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send empty command - should be silently ignored
                empty_command = {"type": "command", "command": ""}
                websocket.send_json(empty_command)

                # Send whitespace-only command - should also be ignored
                whitespace_command = {"type": "command", "command": "   "}
                websocket.send_json(whitespace_command)

                # Connection should remain stable (no error response expected)
                # The test passes if no exception is raised

    def test_websocket_rcon_filtering(self, client, mock_instance):
        """Test RCON log filtering functionality."""
        server_id, instance = mock_instance

        # Set up logs with RCON content
        rcon_logs = (
            "[10:30:21] [Server thread/INFO]: Starting minecraft server version 1.20.4\n"
            "[10:30:22] [RCON Listener #1/INFO]: RCON running on 0.0.0.0:25575\n"
            '[10:30:23] [Server thread/INFO]: Done (1.234s)! For help, type "help"\n'
        )

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
            mock_docker_client.logs_content = rcon_logs
            mock_docker_client_class.return_value = mock_docker_client

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs (should be filtered by default)
                initial_data = websocket.receive_json()

                if initial_data["type"] == "log":
                    # RCON lines should be filtered out by default
                    assert "RCON" not in initial_data["content"]
                    assert "Starting minecraft server" in initial_data["content"]
                    assert "Done" in initial_data["content"]

    def test_websocket_no_token(self, client, mock_instance):
        """Test WebSocket connection without authentication token."""
        server_id, _ = mock_instance

        # Should fail when no token is provided
        with pytest.raises(Exception):
            with client.websocket_connect(f"/servers/{server_id}/console") as websocket:
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
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # 1. Receive initial logs first
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # 2. Send a command
                websocket.send_json({"type": "command", "command": "list"})

                # 3. Connection should close cleanly when exiting context manager


class TestRconFiltering:
    """Test RCON filtering functions."""

    def test_filter_rcon_line_keeps_normal_log(self):
        """Test that normal log lines are kept."""
        from app.websocket.console import filter_rcon_line

        assert (
            filter_rcon_line("[10:30:21] [Server thread/INFO]: Starting server") is True
        )

    def test_filter_rcon_line_filters_rcon_client(self):
        """Test that RCON Client lines are filtered."""
        from app.websocket.console import filter_rcon_line

        assert (
            filter_rcon_line("[10:30:22] [RCON Client #1/INFO]: Thread client started")
            is False
        )

    def test_filter_rcon_line_filters_rcon_listener(self):
        """Test that RCON Listener lines are filtered."""
        from app.websocket.console import filter_rcon_line

        assert (
            filter_rcon_line("[10:30:22] [RCON Listener #1/INFO]: RCON running")
            is False
        )

    def test_filter_rcon_content_mixed(self):
        """Test filtering mixed content."""
        from app.websocket.console import filter_rcon_content

        content = (
            "[10:30:21] [Server thread/INFO]: Starting server\n"
            "[10:30:22] [RCON Listener #1/INFO]: RCON running\n"
            "[10:30:23] [Server thread/INFO]: Done\n"
        )

        result = filter_rcon_content(content)
        assert "Starting server" in result
        assert "Done" in result
        assert "RCON" not in result

    def test_filter_rcon_content_empty(self):
        """Test filtering empty content."""
        from app.websocket.console import filter_rcon_content

        assert filter_rcon_content("") == ""

    def test_filter_rcon_content_no_rcon(self):
        """Test filtering content with no RCON lines."""
        from app.websocket.console import filter_rcon_content

        content = (
            "[10:30:21] [Server thread/INFO]: Starting server\n"
            "[10:30:23] [Server thread/INFO]: Done\n"
        )

        result = filter_rcon_content(content)
        assert result == content


if __name__ == "__main__":
    pytest.main([__file__])
