"""
Integrated tests for ResticSettings configuration integration.

These tests verify that the ResticSettings Pydantic model works correctly
with the ResticManager initialization and configuration handling.

IMPORTANT: These tests do not require restic to be installed.
Run with: poetry run pytest tests/snapshots/test_snapshots_settings_integrated.py -v
"""

import pytest

from app.config import ResticSettings
from app.snapshots import ResticManager


class TestResticSettingsIntegration:
    """Test integration with configuration"""

    def test_restic_settings_model(self):
        """Test ResticSettings Pydantic model"""
        settings = ResticSettings(
            repository_path="/test/repo/path", password="secure-test-password"
        )

        assert settings.repository_path == "/test/repo/path"
        assert settings.password == "secure-test-password"

    def test_restic_manager_initialization(self):
        """Test ResticManager initialization with settings"""
        manager = ResticManager(repository_path="/test/repo", password="test-password")

        assert manager.repository_path == "/test/repo"
        assert manager.password == "test-password"
        assert manager.use_password is True
        assert manager.env["RESTIC_REPOSITORY"] == "/test/repo"
        assert manager.env["RESTIC_PASSWORD"] == "test-password"

    def test_restic_manager_no_password_none(self):
        """Test ResticManager initialization without password (None)"""
        manager = ResticManager(repository_path="/test/repo", password=None)

        assert manager.repository_path == "/test/repo"
        assert manager.password is None
        assert manager.use_password is False
        assert manager.env["RESTIC_REPOSITORY"] == "/test/repo"
        assert "RESTIC_PASSWORD" not in manager.env

    def test_restic_manager_no_password_empty_string(self):
        """Test ResticManager initialization with empty string password"""
        manager = ResticManager(repository_path="/test/repo", password="")

        assert manager.repository_path == "/test/repo"
        assert manager.password == ""
        assert manager.use_password is False
        assert manager.env["RESTIC_REPOSITORY"] == "/test/repo"
        assert "RESTIC_PASSWORD" not in manager.env

    def test_restic_manager_no_password_whitespace(self):
        """Test ResticManager initialization with whitespace-only password"""
        manager = ResticManager(repository_path="/test/repo", password="   ")

        assert manager.repository_path == "/test/repo"
        assert manager.password == "   "
        assert manager.use_password is False
        assert manager.env["RESTIC_REPOSITORY"] == "/test/repo"
        assert "RESTIC_PASSWORD" not in manager.env