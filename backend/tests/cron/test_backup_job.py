"""Tests for backup cron job parameters and registration."""

import pytest

from app.cron.jobs.backup import BackupJobParams, backup_cronjob
from app.cron.registry import cron_registry


class TestBackupJobBasic:
    def test_backup_job_registration(self):
        backup_job = cron_registry.get_cronjob("backup")
        assert backup_job is not None
        assert backup_job.description == "创建备份快照并清理旧快照"
        assert backup_job.schema_cls == BackupJobParams
        assert backup_job.function == backup_cronjob

    def test_backup_params_valid_with_keep_last(self):
        params = BackupJobParams(server_id="test_server", keep_last=5)
        assert params.server_id == "test_server"
        assert params.keep_last == 5
        assert params.enable_forget is True
        assert params.prune is True

    def test_backup_params_valid_with_keep_tag(self):
        params = BackupJobParams(
            server_id="test_server", keep_tag=["important", "weekly"]
        )
        assert params.server_id == "test_server"
        assert params.keep_tag == ["important", "weekly"]
        assert params.enable_forget is True

    def test_backup_params_valid_with_multiple_policies(self):
        params = BackupJobParams(
            server_id="test_server",
            keep_last=10,
            keep_daily=7,
            keep_weekly=4,
            keep_tag=["important"],
        )
        assert params.server_id == "test_server"
        assert params.keep_last == 10
        assert params.keep_daily == 7
        assert params.keep_weekly == 4
        assert params.keep_tag == ["important"]

    def test_backup_params_valid_with_forget_disabled(self):
        params = BackupJobParams(server_id="test_server", enable_forget=False)
        assert params.server_id == "test_server"
        assert params.enable_forget is False

    def test_backup_params_invalid_no_retention_policy(self):
        with pytest.raises(
            ValueError, match="启用forget时至少需要指定一个保留策略参数"
        ):
            BackupJobParams(server_id="test_server", enable_forget=True)

    def test_backup_params_invalid_path_without_server_id(self):
        with pytest.raises(ValueError, match="不能在未指定server_id的情况下指定路径"):
            BackupJobParams(path="/data", keep_last=1)

    def test_backup_params_valid_global_backup(self):
        params = BackupJobParams(keep_daily=7)
        assert params.server_id is None
        assert params.path is None
        assert params.keep_daily == 7

    def test_backup_params_valid_with_keep_within(self):
        params = BackupJobParams(server_id="test_server", keep_within="2y5m7d3h")
        assert params.server_id == "test_server"
        assert params.keep_within == "2y5m7d3h"

    def test_backup_params_prune_option(self):
        params = BackupJobParams(server_id="test_server", keep_last=5, prune=False)
        assert params.prune is False

    def test_backup_params_empty_keep_tag_list(self):
        with pytest.raises(
            ValueError, match="启用forget时至少需要指定一个保留策略参数"
        ):
            BackupJobParams(server_id="test_server", keep_tag=[], enable_forget=True)

    def test_backup_params_complex_scenario(self):
        params = BackupJobParams(
            server_id="minecraft_server",
            path="world",
            keep_daily=30,
            keep_weekly=12,
            keep_monthly=6,
            prune=True,
        )
        assert params.server_id == "minecraft_server"
        assert params.path == "world"
        assert params.keep_daily == 30
        assert params.keep_weekly == 12
        assert params.keep_monthly == 6
        assert params.prune is True
