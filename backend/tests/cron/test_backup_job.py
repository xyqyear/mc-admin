"""
Tests for the backup cron job functionality.

These tests verify the backup job parameters and registration.
"""

import pytest

from app.cron.jobs.backup import BackupJobParams, backup_cronjob
from app.cron.registry import cron_registry


class TestBackupJobBasic:
    """Test backup cron job basic functionality"""

    def test_backup_job_registration(self):
        """Test that backup job is registered correctly"""
        backup_job = cron_registry.get_cronjob("backup")
        assert backup_job is not None
        assert backup_job.description == "创建备份快照并清理旧快照"
        assert backup_job.schema_cls == BackupJobParams
        assert backup_job.function == backup_cronjob

    def test_backup_params_valid_with_keep_last(self):
        """Test valid backup parameters with keep_last"""
        params = BackupJobParams(server_id="test_server", keep_last=5)
        assert params.server_id == "test_server"
        assert params.keep_last == 5
        assert params.enable_forget is True
        assert params.prune is True

    def test_backup_params_valid_with_keep_tag(self):
        """Test valid backup parameters with keep_tag"""
        params = BackupJobParams(
            server_id="test_server",
            keep_tag=["important", "weekly"]
        )
        assert params.server_id == "test_server"
        assert params.keep_tag == ["important", "weekly"]
        assert params.enable_forget is True

    def test_backup_params_valid_with_multiple_policies(self):
        """Test valid backup parameters with multiple retention policies"""
        params = BackupJobParams(
            server_id="test_server",
            keep_last=10,
            keep_daily=7,
            keep_weekly=4,
            keep_tag=["important"]
        )
        assert params.server_id == "test_server"
        assert params.keep_last == 10
        assert params.keep_daily == 7
        assert params.keep_weekly == 4
        assert params.keep_tag == ["important"]

    def test_backup_params_valid_with_forget_disabled(self):
        """Test valid backup parameters with forget disabled"""
        params = BackupJobParams(server_id="test_server", enable_forget=False)
        assert params.server_id == "test_server"
        assert params.enable_forget is False

    def test_backup_params_invalid_no_retention_policy(self):
        """Test that validation fails when forget is enabled but no retention policy is specified"""
        with pytest.raises(ValueError, match="启用forget时至少需要指定一个保留策略参数"):
            BackupJobParams(server_id="test_server", enable_forget=True)

    def test_backup_params_invalid_path_without_server_id(self):
        """Test that validation fails when path is specified without server_id"""
        with pytest.raises(ValueError, match="不能在未指定server_id的情况下指定路径"):
            BackupJobParams(path="/data", keep_last=1)

    def test_backup_params_valid_global_backup(self):
        """Test valid parameters for global backup (no server_id)"""
        params = BackupJobParams(keep_daily=7)
        assert params.server_id is None
        assert params.path is None
        assert params.keep_daily == 7

    def test_backup_params_valid_with_keep_within(self):
        """Test valid backup parameters with keep_within"""
        params = BackupJobParams(
            server_id="test_server",
            keep_within="2y5m7d3h"
        )
        assert params.server_id == "test_server"
        assert params.keep_within == "2y5m7d3h"

    def test_backup_params_prune_option(self):
        """Test prune option can be disabled"""
        params = BackupJobParams(server_id="test_server", keep_last=5, prune=False)
        assert params.prune is False

    def test_backup_params_empty_keep_tag_list(self):
        """Test that empty keep_tag list is handled correctly"""
        with pytest.raises(ValueError, match="启用forget时至少需要指定一个保留策略参数"):
            BackupJobParams(server_id="test_server", keep_tag=[], enable_forget=True)

    def test_backup_params_complex_scenario(self):
        """Test complex backup scenario with server and path"""
        params = BackupJobParams(
            server_id="minecraft_server",
            path="world",
            keep_daily=30,
            keep_weekly=12,
            keep_monthly=6,
            prune=True
        )
        assert params.server_id == "minecraft_server"
        assert params.path == "world"
        assert params.keep_daily == 30
        assert params.keep_weekly == 12
        assert params.keep_monthly == 6
        assert params.prune is True