"""
Test the RCON filtering functionality in the backend.
"""

import pytest
from app.minecraft import MCInstance


class TestRconFiltering:
    """Test RCON filtering functionality."""

    def test_filter_rcon_logs_basic(self):
        """Test basic RCON log filtering."""
        content = """[15:30:01] [Server thread/INFO]: Starting minecraft server version 1.20.1
[15:30:02] [RCON Client] [INFO]: Client connected
[15:30:03] [Server thread/INFO]: Loading properties  
[15:30:04] [RCON Listener] [INFO]: Listening on port 25575
[15:30:05] [Server thread/INFO]: Done (3.2s)! For help, type "help"
[15:30:06] [RCON Client] [INFO]: Command received: list
"""
        
        expected = """[15:30:01] [Server thread/INFO]: Starting minecraft server version 1.20.1
[15:30:03] [Server thread/INFO]: Loading properties  
[15:30:05] [Server thread/INFO]: Done (3.2s)! For help, type "help"
"""
        
        result = MCInstance.filter_rcon_logs(content)
        assert result.strip() == expected.strip()

    def test_filter_rcon_logs_empty(self):
        """Test RCON filtering with empty content."""
        result = MCInstance.filter_rcon_logs("")
        assert result == ""

    def test_filter_rcon_logs_no_rcon(self):
        """Test RCON filtering with no RCON logs."""
        content = """[15:30:01] [Server thread/INFO]: Starting minecraft server
[15:30:02] [Server thread/INFO]: Loading properties
[15:30:03] [Server thread/INFO]: Done!
"""
        result = MCInstance.filter_rcon_logs(content)
        assert result == content

    def test_filter_rcon_logs_all_rcon(self):
        """Test RCON filtering when all logs are RCON-related."""
        content = """[15:30:01] [RCON Client] [INFO]: Client connected
[15:30:02] [RCON Listener] [INFO]: Listening on port 25575
[15:30:03] [RCON Client] [INFO]: Command received: list
[15:30:04] [RCON Client] [INFO]: Client disconnected
"""
        
        # Should result in empty string since all lines are filtered
        result = MCInstance.filter_rcon_logs(content)
        expected = ""
        assert result == expected

    def test_filter_rcon_logs_mixed_case(self):
        """Test RCON filtering with different cases (should be case sensitive)."""
        content = """[15:30:01] [Server thread/INFO]: Starting server
[15:30:02] [RCON CLIENT] [INFO]: This should NOT be filtered (different case)
[15:30:03] [RCON Client] [INFO]: This SHOULD be filtered (exact case)
[15:30:04] [rcon client] [INFO]: This should NOT be filtered (different case)
[15:30:05] [Server thread/INFO]: Done!
"""
        
        expected = """[15:30:01] [Server thread/INFO]: Starting server
[15:30:02] [RCON CLIENT] [INFO]: This should NOT be filtered (different case)
[15:30:04] [rcon client] [INFO]: This should NOT be filtered (different case)
[15:30:05] [Server thread/INFO]: Done!
"""
        
        result = MCInstance.filter_rcon_logs(content)
        assert result == expected


if __name__ == "__main__":
    pytest.main([__file__])