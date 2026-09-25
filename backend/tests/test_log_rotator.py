"""
Tests for log rotation functionality.

Tests the custom rotator function that compresses log files using gzip
when they are rotated by TimedRotatingFileHandler.
"""

import gzip
import logging
import logging.handlers
from contextlib import closing

from app.logger import rotator


class TestLogRotation:
    """Test log file rotation and compression with real logger."""

    def test_log_rotation_with_compression(self, tmp_path):
        """Test that logger rotates and compresses log files correctly."""
        log_file = tmp_path / "test.log"
        test_logger = logging.getLogger(f"test_rotation.{tmp_path}")
        test_logger.setLevel(logging.INFO)

        with closing(logging.handlers.TimedRotatingFileHandler(
            log_file, when="S", backupCount=5
        )) as handler:
            handler.rotator = rotator
            test_logger.addHandler(handler)
            try:
                for i in range(10):
                    test_logger.info(f"Test log message {i}")

                handler.doRollover()

                for i in range(10, 20):
                    test_logger.info(f"Test log message {i}")

                assert log_file.exists()
                compressed_files = list(tmp_path.glob("*.gz"))
                assert len(compressed_files) > 0, "No compressed log file found"

                with gzip.open(compressed_files[0], "rt", encoding="utf-8") as f:
                    content = f.read()
                    assert "Test log message 0" in content
                    assert "Test log message 9" in content
                    assert "Test log message 10" not in content

                with open(log_file, "r", encoding="utf-8") as f:
                    current_content = f.read()
                    assert "Test log message 10" in current_content
                    assert "Test log message 19" in current_content
            finally:
                test_logger.removeHandler(handler)
