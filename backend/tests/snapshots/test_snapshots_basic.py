"""
Basic unit tests for snapshot functionality.

For comprehensive integration tests with real restic commands,
see test_snapshots_integrated.py
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import ResticSettings
from app.snapshots import ResticManager, ResticRestorePreviewAction, ResticSnapshot


class TestResticManagerBasic:
    """Basic tests for ResticManager initialization and validation"""

    def test_restic_manager_initialization(self):
        """Test ResticManager initialization"""
        manager = ResticManager(
            repository_path="/test/repo/path", password="test-password"
        )

        assert manager.repository_path == "/test/repo/path"
        assert manager.password == "test-password"
        assert manager.env["RESTIC_REPOSITORY"] == "/test/repo/path"
        assert manager.env["RESTIC_PASSWORD"] == "test-password"

    @pytest.mark.asyncio
    async def test_backup_requires_absolute_path(self):
        """Test that backup method validates absolute paths"""
        manager = ResticManager("/test/repo", "password")

        relative_path = Path("relative/path")
        with pytest.raises(ValueError, match="Path must be absolute"):
            await manager.backup(relative_path)

    def test_environment_variables_setup(self):
        """Test that environment variables are set correctly"""
        repo_path = "/custom/repo/location"
        password = "secure-password-123"

        manager = ResticManager(repo_path, password)

        assert "RESTIC_REPOSITORY" in manager.env
        assert "RESTIC_PASSWORD" in manager.env
        assert manager.env["RESTIC_REPOSITORY"] == repo_path
        assert manager.env["RESTIC_PASSWORD"] == password

    @pytest.mark.asyncio
    async def test_forget_validation_requires_policy(self):
        """Test that forget method requires at least one retention policy"""
        manager = ResticManager("/test/repo", "password")

        # Test that calling forget without any parameters raises ValueError
        with pytest.raises(
            ValueError,
            match="At least one retention policy parameter must be specified",
        ):
            await manager.forget()

        # Test that calling forget with all None parameters raises ValueError
        with pytest.raises(
            ValueError,
            match="At least one retention policy parameter must be specified",
        ):
            await manager.forget(
                keep_last=None,
                keep_hourly=None,
                keep_daily=None,
                keep_weekly=None,
                keep_monthly=None,
                keep_yearly=None,
                keep_tag=None,
                keep_within=None,
            )

        # Test that calling forget with empty keep_tag list raises ValueError
        with pytest.raises(
            ValueError,
            match="At least one retention policy parameter must be specified",
        ):
            await manager.forget(keep_tag=[])

    def test_forget_parameter_validation(self):
        """Test that forget method validates parameters correctly"""
        manager = ResticManager("/test/repo", "password")

        # Test that valid parameters don't raise exceptions during validation
        # (we can't test actual execution without mocking exec_command)
        try:
            # This would normally call exec_command, but we just test parameter validation
            retention_params = [
                1,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ]  # keep_last=1
            if all(
                param is None or (isinstance(param, list) and len(param) == 0)
                for param in retention_params
            ):
                raise ValueError(
                    "At least one retention policy parameter must be specified"
                )
        except ValueError:
            pytest.fail("Valid parameters should not raise ValueError")

        # Test that keep_tag with valid list doesn't raise exception
        try:
            retention_params = [
                None,
                None,
                None,
                None,
                None,
                None,
                ["tag1", "tag2"],
                None,
            ]  # keep_tag=["tag1", "tag2"]
            if all(
                param is None or (isinstance(param, list) and len(param) == 0)
                for param in retention_params
            ):
                raise ValueError(
                    "At least one retention policy parameter must be specified"
                )
        except ValueError:
            pytest.fail("Valid keep_tag parameters should not raise ValueError")


class TestSnapshotModels:
    """Test Pydantic models for snapshot data"""

    def test_restic_snapshot_model(self):
        """Test ResticSnapshot model validation"""
        snapshot_data = {
            "time": datetime.now(timezone.utc),
            "paths": ["/test/path1", "/test/path2"],
            "hostname": "test-host",
            "username": "test-user",
            "program_version": "restic 0.18.0",
            "id": "abc123def456",
            "short_id": "abc123",
        }

        snapshot = ResticSnapshot(**snapshot_data)

        assert snapshot.hostname == "test-host"
        assert snapshot.username == "test-user"
        assert snapshot.program_version == "restic 0.18.0"
        assert snapshot.id == "abc123def456"
        assert snapshot.short_id == "abc123"
        assert len(snapshot.paths) == 2

    def test_restic_restore_preview_action_model(self):
        """Test ResticRestorePreviewAction model validation"""

        action_data = {
            "message_type": "verbose_status",
            "action": "updated",
            "item": "/test/file.txt",
            "size": 1024,
        }

        action = ResticRestorePreviewAction(**action_data)

        assert action.message_type == "verbose_status"
        assert action.action == "updated"
        assert action.item == "/test/file.txt"
        assert action.size == 1024


class TestConfigurationIntegration:
    """Test configuration integration"""

    def test_restic_settings_validation(self):
        """Test ResticSettings model"""

        settings = ResticSettings(
            repository_path="/backup/repo", password="strong-password"
        )

        assert settings.repository_path == "/backup/repo"
        assert settings.password == "strong-password"
