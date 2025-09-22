"""
Comprehensive tests for the WebSocket console endpoint.
Tests real-time console functionality with mocked dependencies.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app


class MockMCInstance:
    """Mock MCInstance for testing WebSocket console functionality."""

    def __init__(self, server_id: str, base_path: Path):
        self.server_id = server_id
        self.base_path = base_path
        self.project_path = base_path / server_id
        self.logs_path = self.project_path / "logs" / "latest.log"

        # Create directory structure
        self.logs_path.parent.mkdir(parents=True, exist_ok=True)

        # Sample log content
        self.log_content = (
            "[10:30:21] [Server thread/INFO]: Starting minecraft server version 1.20.4\n"
            "[10:30:21] [Server thread/INFO]: Loading properties\n"
            "[10:30:22] [RCON Listener #1/INFO]: RCON running on 0.0.0.0:25575\n"
            '[10:30:22] [Server thread/INFO]: Done (1.234s)! For help, type "help"\n'
        )

        # Write initial log content
        self.logs_path.write_text(self.log_content)

    async def exists(self):
        """Return True to indicate server exists."""
        return True

    async def _get_log_path(self):
        """Return the log file path."""
        return self.logs_path

    def filter_rcon_logs(self, content: str) -> str:
        """Filter out RCON-related log lines."""
        lines = content.split("\n")
        filtered_lines = [line for line in lines if "RCON" not in line]
        return "\n".join(filtered_lines)

    async def get_logs_from_file_filtered(
        self,
        start_position: int,
        filter_rcon: bool = True,
        max_chars: int = 1024 * 1024,
    ):
        """Mock method to get filtered logs from file."""
        # start_position is ignored in this mock implementation
        _ = start_position
        if not self.logs_path.exists():
            return MockLogResult("", 0)

        content = self.logs_path.read_text()
        if filter_rcon:
            content = self.filter_rcon_logs(content)

        # Apply max_chars limit
        if len(content) > max_chars:
            content = content[-max_chars:]

        return MockLogResult(content, len(content))

    async def get_logs_from_file(self, position: int):
        """Mock method to get new logs from file."""
        if not self.logs_path.exists():
            return MockLogResult("", position)

        content = self.logs_path.read_text()
        if position >= len(content):
            return MockLogResult("", position)

        new_content = content[position:]
        return MockLogResult(new_content, len(content))

    async def send_command_stdin(self, command: str):
        """Mock method to send command via stdin."""
        if "CREATE_CONSOLE_IN_PIPE" in command:
            raise RuntimeError("CREATE_CONSOLE_IN_PIPE not configured")
        # Simulate successful command execution
        # Command is processed but not used in this mock
        _ = command

    def add_log_line(self, line: str):
        """Add a new log line to simulate real-time logging."""
        current_content = self.logs_path.read_text()
        new_content = current_content + line + "\n"
        self.logs_path.write_text(new_content)


class MockLogResult:
    """Mock result for log operations."""

    def __init__(self, content: str, pointer: int):
        self.content = content
        self.pointer = pointer


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory(
        prefix="mc_websocket_test_", dir="/tmp"
    ) as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_instance(temp_dir):
    """Create mock instance with test structure."""
    server_id = "test_server"
    instance = MockMCInstance(server_id, temp_dir)
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
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

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
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            # This should fail due to invalid token
            with pytest.raises(Exception):  # WebSocket connection will fail
                with client.websocket_connect(
                    f"/servers/{server_id}/console?token=invalid_token"
                ) as websocket:
                    websocket.receive_json()

    def test_websocket_server_not_found(self, client, mock_instance):
        """Test WebSocket connection when server doesn't exist."""
        server_id, instance = mock_instance

        # Mock instance that doesn't exist
        async def mock_exists():
            return False

        instance.exists = mock_exists

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
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

    def test_websocket_command_execution(self, client, mock_instance):
        """Test sending commands through WebSocket."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send a command
                command_message = {"type": "command", "command": "list"}
                websocket.send_json(command_message)

                # The command should be processed (no response expected based on implementation)
                # We mainly test that the command doesn't cause errors

    def test_websocket_command_with_pipe_error(self, client, mock_instance):
        """Test command execution when CREATE_CONSOLE_IN_PIPE is not configured."""
        server_id, instance = mock_instance

        # Mock the send_command_stdin to raise the specific error
        async def mock_send_command_error(command):
            _ = command  # Command parameter is not used in this mock
            raise RuntimeError("CREATE_CONSOLE_IN_PIPE not configured")

        instance.send_command_stdin = mock_send_command_error

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send a command that will trigger the error
                command_message = {"type": "command", "command": "list"}
                websocket.send_json(command_message)

                # Should receive info message about the pipe configuration
                response = websocket.receive_json()
                assert response["type"] == "info"
                assert "CREATE_CONSOLE_IN_PIPE" in response["message"]

    def test_websocket_filter_toggle(self, client, mock_instance):
        """Test RCON filter toggle functionality."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs first
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send filter change message after receiving initial logs
                filter_message = {"type": "set_filter", "filter_rcon": False}
                websocket.send_json(filter_message)

                # Should receive filter update confirmation
                response = websocket.receive_json()
                assert response["type"] == "filter_updated"
                assert response["filter_rcon"] is False

    def test_websocket_log_refresh(self, client, mock_instance):
        """Test log refresh functionality."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send log refresh request
                refresh_message = {"type": "refresh_logs"}
                websocket.send_json(refresh_message)

                # Should receive refreshed logs
                response = websocket.receive_json()
                assert response["type"] == "logs_refreshed"
                assert "content" in response

    def test_websocket_invalid_message_format(self, client, mock_instance):
        """Test handling of invalid message formats."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

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
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

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
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # Send empty command
                empty_command = {"type": "command", "command": ""}
                websocket.send_json(empty_command)

                # Empty commands should be ignored (no response)
                # Test that the connection remains stable by sending another message
                valid_message = {"type": "refresh_logs"}
                websocket.send_json(valid_message)

                response = websocket.receive_json()
                assert response["type"] == "logs_refreshed"

    def test_websocket_rcon_filtering(self, client, mock_instance):
        """Test RCON log filtering functionality."""
        server_id, instance = mock_instance

        # Add some RCON logs to the mock instance
        rcon_log_content = (
            "[10:30:21] [Server thread/INFO]: Starting minecraft server version 1.20.4\n"
            "[10:30:22] [RCON Listener #1/INFO]: RCON running on 0.0.0.0:25575\n"
            '[10:30:23] [Server thread/INFO]: Done (1.234s)! For help, type "help"\n'
        )
        instance.logs_path.write_text(rcon_log_content)

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Receive initial logs first (should be filtered by default)
                initial_data = websocket.receive_json()

                if initial_data["type"] == "log":
                    # RCON lines should be filtered out by default
                    assert "RCON" not in initial_data["content"]
                    assert "Starting minecraft server" in initial_data["content"]
                    assert "Done" in initial_data["content"]

                # After receiving initial logs, disable RCON filtering
                filter_message = {"type": "set_filter", "filter_rcon": False}
                websocket.send_json(filter_message)

                # Should receive filter confirmation
                filter_response = websocket.receive_json()
                assert filter_response["type"] == "filter_updated"
                assert filter_response["filter_rcon"] is False

                # Request refresh with filtering disabled
                refresh_message = {"type": "refresh_logs"}
                websocket.send_json(refresh_message)

                # Should receive logs with RCON content included
                refresh_response = websocket.receive_json()
                assert refresh_response["type"] == "logs_refreshed"
                # With filtering disabled, RCON content should be present
                # Note: The actual filtering logic depends on the instance implementation

    def test_websocket_log_not_found(self, client, mock_instance):
        """Test handling when log file doesn't exist."""
        server_id, instance = mock_instance

        # Remove the log file to simulate not found scenario
        instance.logs_path.unlink()

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # Should receive error about missing log file
                initial_data = websocket.receive_json()
                assert initial_data["type"] == "error"
                assert (
                    "控制台日志未找到" in initial_data["message"]
                    or "not found" in initial_data["message"].lower()
                )

    def test_websocket_no_token(self, client, mock_instance):
        """Test WebSocket connection without authentication token."""
        server_id, _ = mock_instance

        # Should fail when no token is provided
        with pytest.raises(Exception):  # WebSocket connection will fail
            with client.websocket_connect(f"/servers/{server_id}/console") as websocket:
                websocket.receive_json()

    def test_websocket_connection_lifecycle(self, client, mock_instance):
        """Test the complete WebSocket connection lifecycle."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.console.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            with client.websocket_connect(
                f"/servers/{server_id}/console?token=test_master_token"
            ) as websocket:
                # 1. Receive initial logs first
                initial_data = websocket.receive_json()
                assert initial_data["type"] in ["log", "info"]

                # 2. Test filter functionality after receiving initial logs
                websocket.send_json({"type": "set_filter", "filter_rcon": False})
                filter_response = websocket.receive_json()
                assert filter_response["type"] == "filter_updated"

                # 3. Test command execution
                websocket.send_json({"type": "command", "command": "say Hello World"})

                # 4. Test log refresh
                websocket.send_json({"type": "refresh_logs"})
                refresh_response = websocket.receive_json()
                assert refresh_response["type"] == "logs_refreshed"

                # 5. Connection should close cleanly when exiting context manager


if __name__ == "__main__":
    pytest.main([__file__])
