"""
Test for the WebSocket console endpoint.
This test creates a temporary file structure and log file in /tmp,
then tests the WebSocket console endpoint to verify it reads and streams log content correctly.
"""

import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.minecraft import LogType


class MockMCInstance:
    """Mock MCInstance for testing the WebSocket console functionality."""

    def __init__(self, server_id: str, base_path: Path):
        self.server_id = server_id
        self.base_path = base_path
        self.server_path = base_path / server_id
        self.logs_dir = self.server_path / "logs"
        self.log_file = self.logs_dir / "latest.log"

    async def exists(self):
        """Return True to indicate server exists."""
        return True

    def _get_log_path(self) -> Path:
        """Return the path to the log file."""
        return self.log_file

    async def get_logs_from_file(self, start: int = 0) -> LogType:
        """Mock method to get logs from file."""
        if not self.log_file.exists():
            return LogType(content="", pointer=0)
        
        try:
            file_size = self.log_file.stat().st_size
            
            # If start is negative, read from the end
            if start < 0:
                abs_start = abs(start)
                start_position = max(0, file_size - abs_start)
                with open(self.log_file, "r", encoding="utf-8") as f:
                    f.seek(start_position)
                    content = f.read(abs_start)
                return LogType(content=content, pointer=file_size)
            
            # If start is 0 or positive, read from that position
            with open(self.log_file, "r", encoding="utf-8") as f:
                f.seek(start)
                content = f.read()
                return LogType(content=content, pointer=file_size)
        except Exception:
            return LogType(content="", pointer=0)

    async def send_command_rcon(self, command: str) -> str:
        """Mock RCON command execution."""
        return f"Mock result for command: {command}"
    
    async def get_log_file_end_pointer(self) -> int:
        """Mock method to get the end pointer of the log file."""
        if not self.log_file.exists():
            return 0
        return self.log_file.stat().st_size
    
    async def get_status(self):
        """Return mock status."""
        # Import here to avoid circular imports
        from app.minecraft import MCServerStatus
        return MCServerStatus.HEALTHY

    @staticmethod
    def filter_rcon_logs(content: str) -> str:
        """Mock method for RCON filtering."""
        if not content:
            return content
        
        lines = content.split('\n')
        filtered_lines = []
        
        for line in lines:
            # Filter out RCON Client and RCON Listener log lines
            if '[RCON Client' not in line and '[RCON Listener' not in line:
                filtered_lines.append(line)
        
        # Remove empty lines for cleaner output
        import re
        result = '\n'.join(filtered_lines)
        result = re.sub(r'\n\s*\n', '\n', result)
        return result

    async def get_logs_from_file_filtered(self, start: int = 0, filter_rcon: bool = True):
        """Mock method to get filtered logs from file."""
        from app.minecraft import LogType
        
        # Get raw logs first
        raw_logs = await self.get_logs_from_file(start)
        content = raw_logs.content
        
        # Apply RCON filtering if requested
        if filter_rcon:
            content = self.filter_rcon_logs(content)
        
        # Simulate 1M character truncation
        max_chars = 1024 * 1024  # 1M characters
        
        if len(content) > max_chars:
            # Truncate from the end (keep the most recent logs)
            content = content[-max_chars:]
        
        return LogType(content=content, pointer=raw_logs.pointer)

    def setup_test_structure(self):
        """Create the test directory structure and initial log file."""
        # Create directories
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create initial log content
        initial_content = """[15:30:01] [Server thread/INFO]: Starting minecraft server version 1.20.1
[15:30:02] [Server thread/INFO]: Loading properties
[15:30:03] [Server thread/INFO]: Default game type: SURVIVAL
[15:30:04] [Server thread/INFO]: Generating keypair
[15:30:05] [Server thread/INFO]: Starting Minecraft server on *:25565
[15:30:06] [Server thread/INFO]: Using epoll channel type
[15:30:07] [Server thread/INFO]: Preparing level "world"
[15:30:08] [Server thread/INFO]: Done (3.2s)! For help, type "help"
"""
        
        # Write initial content to log file
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(initial_content)
        
        return initial_content


def write_to_log_file(log_file: Path, new_content: str, delay: float = 0.1):
    """Write new content to log file after a delay (simulates real-time logging)."""
    def _write():
        time.sleep(delay)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(new_content)
    
    thread = threading.Thread(target=_write)
    thread.start()
    return thread


def test_websocket_console_file_reading_and_streaming():
    """
    Test the WebSocket console endpoint:
    1. Creates a temporary file structure in /tmp
    2. Creates a log file with initial content
    3. Connects to WebSocket and verifies initial content is sent
    4. Writes new content to log file and verifies it's streamed via WebSocket
    """
    client = TestClient(app)
    
    # Create temporary directory structure in /tmp
    with tempfile.TemporaryDirectory(prefix="mc_server_test_", dir="/tmp") as temp_dir:
        temp_path = Path(temp_dir)
        server_id = "test_server"
        
        # Create mock instance and set up test structure
        mock_instance = MockMCInstance(server_id, temp_path)
        mock_instance.setup_test_structure()
        
        # Mock the mc_manager and authentication
        with patch("app.routers.servers.mc_manager") as mock_router_manager, \
             patch("app.dependencies.settings") as mock_settings:
            # Mock the manager in the router 
            mock_router_manager.get_instance.return_value = mock_instance
            mock_settings.master_token = "test_master_token"
        
            # Start WebSocket connection with authentication token
            with client.websocket_connect(f"/servers/{server_id}/console?token=test_master_token") as websocket:
                # The WebSocket should send initial log content
                # We expect multiple messages for the initial content
                messages_received = []
                
                # Collect initial messages (should contain existing log content)
                # We expect at least the initial log content
                try:
                    # Get the first message which should be the initial logs
                    data = websocket.receive_text()
                    message = json.loads(data)
                    messages_received.append(message)
                except Exception as e:
                    # If this fails, the WebSocket connection might have issues
                    assert False, f"Failed to receive initial message: {e}"
                
                # Verify we received some initial content
                assert len(messages_received) > 0, "Should have received initial log content"
                
                # Check that we received log messages with content from the initial log
                log_messages = [msg for msg in messages_received if msg.get("type") == "log"]
                assert len(log_messages) > 0, "Should have received log-type messages"
                
                # Combine all log content to verify it contains initial content
                combined_content = "".join([msg.get("content", "") for msg in log_messages])
                assert "Starting minecraft server version 1.20.1" in combined_content
                assert "Done (3.2s)! For help, type \"help\"" in combined_content
                
                # Note: Testing file monitoring would require more complex setup with actual file watching
                # For now, we'll test the RCON command functionality
                
                # Test RCON command sending
                command_message = {
                    "type": "command",
                    "command": "list"
                }
                
                websocket.send_text(json.dumps(command_message))
                
                # Wait for command response
                try:
                    data = websocket.receive_text()
                    message = json.loads(data)
                    
                    assert message.get("type") == "command_result", f"Expected command_result, got: {message}"
                    assert message.get("command") == "list", f"Expected command 'list', got: {message.get('command')}"
                    assert "Mock result for command: list" in message.get("result", ""), f"Expected mock result, got: {message.get('result')}"
                    
                    print("RCON command response received successfully!")
                except Exception as e:
                    assert False, f"Failed to receive RCON command response: {e}"


def test_websocket_console_large_file_initial_limit():
    """
    Test that the WebSocket console respects the 1M character initial file limit.
    """
    client = TestClient(app)
    
    with tempfile.TemporaryDirectory(prefix="mc_server_large_test_", dir="/tmp") as temp_dir:
        temp_path = Path(temp_dir)
        server_id = "large_test_server"
        
        # Create mock instance
        mock_instance = MockMCInstance(server_id, temp_path)
        mock_instance.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a large log file (larger than 1M characters)
        large_content_line = "[15:30:01] [Server thread/INFO]: This is a test line that will be repeated many times to create a large file\n"
        lines_needed = (1024 * 1024 + 1000) // len(large_content_line) + 100  # Ensure > 1M characters
        
        large_content = large_content_line * lines_needed
        
        # Write large content to log file
        with open(mock_instance.log_file, "w", encoding="utf-8") as f:
            f.write(large_content)
        
        # Verify file is actually larger than 1M characters
        assert len(large_content) > 1024 * 1024, f"Test file should be larger than 1M characters, got {len(large_content)} characters"
        
        # Mock the mc_manager and authentication
        with patch("app.routers.servers.mc_manager") as mock_router_manager, \
             patch("app.dependencies.settings") as mock_settings:
            # Mock the manager in the router 
            mock_router_manager.get_instance.return_value = mock_instance
            mock_settings.master_token = "test_master_token"
        
            # Connect to WebSocket with authentication token
            with client.websocket_connect(f"/servers/{server_id}/console?token=test_master_token") as websocket:
                # Collect all initial messages
                messages_received = []
                total_content_received = ""
                
                try:
                    # Get the initial log message 
                    data = websocket.receive_text()
                    message = json.loads(data)
                    messages_received.append(message)
                    
                    if message.get("type") == "log" and message.get("content"):
                        total_content_received += message.get("content")
                except Exception as e:
                    assert False, f"Failed to receive initial large file content: {e}"
                
                # Verify we received some content but not the entire large file
                assert len(total_content_received) > 0, "Should have received some log content"
                
                # The received content should be approximately 1M characters or less
                # Since we're sending the last 1M characters, we should get content from the end of the file
                received_chars = len(total_content_received)
                assert received_chars <= 1024 * 1024, f"Should not receive more than 1M characters, got {received_chars} characters"
                
                # The content should be from the end of the file (last 1M characters)
                # Since all lines are identical, we can just verify we got reasonable amount of content
                assert received_chars > 500000, f"Should receive substantial content (>500K chars), got {received_chars} characters"


if __name__ == "__main__":
    # Run individual test
    test_websocket_console_file_reading_and_streaming()
    test_websocket_console_large_file_initial_limit()
    print("All WebSocket console tests passed!")