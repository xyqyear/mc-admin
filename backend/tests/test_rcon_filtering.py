"""
Test the RCON filtering functionality in the console module.
"""

import pytest

from app.websocket.console import filter_rcon_content, filter_rcon_line


class TestRconFiltering:
    """Test RCON filtering functionality."""

    def test_filter_rcon_line_basic(self):
        """Test basic RCON line filtering."""
        # Normal server logs should pass
        assert (
            filter_rcon_line("[15:30:01] [Server thread/INFO]: Starting server") is True
        )
        assert (
            filter_rcon_line("[15:30:03] [Server thread/INFO]: Loading properties")
            is True
        )
        assert filter_rcon_line("[15:30:05] [Server thread/INFO]: Done!") is True

        # RCON Client and Listener logs should be filtered
        assert (
            filter_rcon_line("[15:30:02] [RCON Client #1/INFO]: Client connected")
            is False
        )
        assert (
            filter_rcon_line(
                "[15:30:04] [RCON Listener #1/INFO]: Listening on port 25575"
            )
            is False
        )

    def test_filter_rcon_content_basic(self):
        """Test basic RCON content filtering."""
        content = (
            "[15:30:01] [Server thread/INFO]: Starting minecraft server version 1.20.1\n"
            "[15:30:02] [RCON Client #1/INFO]: Client connected\n"
            "[15:30:03] [Server thread/INFO]: Loading properties\n"
            "[15:30:04] [RCON Listener #1/INFO]: Listening on port 25575\n"
            '[15:30:05] [Server thread/INFO]: Done (3.2s)! For help, type "help"\n'
            "[15:30:06] [RCON Client #1/INFO]: Command received: list\n"
        )

        result = filter_rcon_content(content)
        assert "Starting minecraft server" in result
        assert "Loading properties" in result
        assert "Done (3.2s)" in result
        assert "RCON Client" not in result
        assert "RCON Listener" not in result

    def test_filter_rcon_content_empty(self):
        """Test RCON filtering with empty content."""
        result = filter_rcon_content("")
        assert result == ""

    def test_filter_rcon_content_no_rcon(self):
        """Test RCON filtering with no RCON logs."""
        content = (
            "[15:30:01] [Server thread/INFO]: Starting minecraft server\n"
            "[15:30:02] [Server thread/INFO]: Loading properties\n"
            "[15:30:03] [Server thread/INFO]: Done!\n"
        )
        result = filter_rcon_content(content)
        assert result == content

    def test_filter_rcon_content_all_rcon(self):
        """Test RCON filtering when all logs are RCON-related."""
        content = (
            "[15:30:01] [RCON Client #1/INFO]: Client connected\n"
            "[15:30:02] [RCON Listener #1/INFO]: Listening on port 25575\n"
            "[15:30:03] [RCON Client #1/INFO]: Command received: list\n"
            "[15:30:04] [RCON Client #1/INFO]: Client disconnected\n"
        )

        # Should result in empty lines since all content is filtered
        result = filter_rcon_content(content)
        assert "RCON" not in result

    def test_filter_rcon_content_mixed_case(self):
        """Test RCON filtering with different cases (should be case sensitive)."""
        content = (
            "[15:30:01] [Server thread/INFO]: Starting server\n"
            "[15:30:02] [RCON CLIENT #1/INFO]: This should NOT be filtered (different case)\n"
            "[15:30:03] [RCON Client #1/INFO]: This SHOULD be filtered (matches pattern)\n"
            "[15:30:04] [rcon client #1/INFO]: This should NOT be filtered (different case)\n"
            "[15:30:05] [Server thread/INFO]: Done!\n"
        )

        result = filter_rcon_content(content)
        # Lines with exact pattern should be filtered
        assert "[RCON Client #1" not in result
        # Lines with different case should remain
        assert "[RCON CLIENT" in result
        assert "[rcon client" in result
        # Normal lines should remain
        assert "Starting server" in result
        assert "Done!" in result

    def test_filter_rcon_line_with_various_patterns(self):
        """Test RCON filtering with various RCON patterns."""
        # RCON Listener patterns
        assert (
            filter_rcon_line(
                "[10:00:00] [RCON Listener #1/INFO]: RCON running on 0.0.0.0:25575"
            )
            is False
        )
        assert (
            filter_rcon_line(
                "[10:00:00] [RCON Listener #1/INFO]: Thread RCON Listener #1 started"
            )
            is False
        )

        # RCON Client patterns
        assert (
            filter_rcon_line(
                "[10:00:00] [RCON Client /127.0.0.1 #1/INFO]: Thread RCON Client started"
            )
            is False
        )
        assert (
            filter_rcon_line(
                "[10:00:00] [RCON Client /127.0.0.1 #2/INFO]: Thread RCON Client started"
            )
            is False
        )


if __name__ == "__main__":
    pytest.main([__file__])
