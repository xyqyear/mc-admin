"""
Tests for log rotation functionality.

Tests the custom rotator function that compresses log files using gzip
when they are rotated by TimedRotatingFileHandler.
"""

import gzip
import logging
import logging.handlers

from app.logger import rotator


class TestLogRotation:
    """Test log file rotation and compression with real logger."""

    def test_log_rotation_with_compression(self, tmp_path):
        """Test that logger rotates and compresses log files correctly."""
        # Create a test logger with rotating file handler
        log_file = tmp_path / "test.log"

        test_logger = logging.getLogger("test_rotation")
        test_logger.setLevel(logging.INFO)
        test_logger.handlers.clear()  # Clear any existing handlers

        # Create rotating handler with our rotator
        handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when="S",  # Rotate every second for testing
            backupCount=5
        )
        handler.rotator = rotator
        test_logger.addHandler(handler)

        # Write some log messages
        for i in range(10):
            test_logger.info(f"Test log message {i}")

        # Force rotation by calling doRollover
        handler.doRollover()

        # Write more messages after rotation
        for i in range(10, 20):
            test_logger.info(f"Test log message {i}")

        # Check that the main log file exists
        assert log_file.exists()

        # Find the compressed rotated file (should end with .gz)
        compressed_files = list(tmp_path.glob("*.gz"))
        assert len(compressed_files) > 0, "No compressed log file found"

        # Verify the compressed file can be read
        compressed_file = compressed_files[0]
        with gzip.open(compressed_file, "rt", encoding="utf-8") as f:
            content = f.read()
            # Should contain the first batch of messages
            assert "Test log message 0" in content
            assert "Test log message 9" in content
            # Should NOT contain the second batch
            assert "Test log message 10" not in content

        # Verify current log file contains new messages
        with open(log_file, "r", encoding="utf-8") as f:
            current_content = f.read()
            assert "Test log message 10" in current_content
            assert "Test log message 19" in current_content

        # Cleanup
        test_logger.handlers.clear()
