from typing import Annotated, Any, ClassVar

from pydantic import ConfigDict, Field, model_validator

from ...self_check.constants import CHECK_IDS, CHECK_LABELS
from ...self_check.jar_metadata import normalize_jar_id
from ..schemas import BaseConfigSchema


def default_backup_mod_ids() -> list[str]:
    return [
        "advancedbackups",
        "aromabackup",
        "aromabackuprecovery",
        "backupmanager",
        "backuper",
        "drivebackupv2",
        "ebackup",
        "fastback",
        "ftbbackups",
        "ftbbackups2",
        "ftbbackups3",
        "quickbackupmulti_reforged",
        "serverbackup",
        "simplebackups",
        "simplebackup",
        "textile_backup",
        "x-backup",
    ]


class SelfCheckEnabledChecksConfig(BaseConfigSchema):
    model_config = ConfigDict(title="自检项开关")

    CHECK_FIELD_BY_ID: ClassVar[dict[str, str]] = {
        "backup.restic_configured": "backup_restic_configured",
        "backup.restic_reachable": "backup_restic_reachable",
        "backup.server_snapshot_coverage": "backup_server_snapshot_coverage",
        "backup.server_snapshot_freshness": "backup_server_snapshot_freshness",
        "storage.backup_repository_usage": "storage_backup_repository_usage",
        "storage.server_directory_usage": "storage_server_directory_usage",
        "locks.python_restic_active": "locks_python_restic_active",
        "locks.repo_restic_active": "locks_repo_restic_active",
        "dns.drift": "dns_drift",
        "dependency.binaries": "dependency_binaries",
        "log_monitor.active": "log_monitor_active",
        "server.backup_mod_removed": "server_backup_mod_removed",
        "files.permission_consistency": "files_permission_consistency",
        "server.filesystem_db_sync": "server_filesystem_db_sync",
    }

    backup_restic_configured: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["backup.restic_configured"],
            description="是否检查 Restic 相关配置是否存在。",
        ),
    ] = True
    backup_restic_reachable: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["backup.restic_reachable"],
            description="是否检查 Restic 仓库是否可以查询。",
        ),
    ] = True
    backup_server_snapshot_coverage: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["backup.server_snapshot_coverage"],
            description="是否检查每台运行中服务器是否至少被一个快照覆盖。",
        ),
    ] = True
    backup_server_snapshot_freshness: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["backup.server_snapshot_freshness"],
            description="是否检查已覆盖服务器的最新快照是否足够新。",
        ),
    ] = True
    storage_backup_repository_usage: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["storage.backup_repository_usage"],
            description="是否检查 Restic 备份仓库所在磁盘的使用率。",
        ),
    ] = True
    storage_server_directory_usage: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["storage.server_directory_usage"],
            description="是否检查服务器目录所在磁盘的使用率。",
        ),
    ] = True
    locks_python_restic_active: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["locks.python_restic_active"],
            description="是否展示 Python 代码中当前活动的备份或恢复锁。",
        ),
    ] = True
    locks_repo_restic_active: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["locks.repo_restic_active"],
            description="是否展示 Restic 仓库内部当前活动的锁条目。",
        ),
    ] = True
    dns_drift: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["dns.drift"],
            description="是否检查 DNS 记录和 MC Router 路由是否与运行中服务器一致。",
        ),
    ] = True
    dependency_binaries: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["dependency.binaries"],
            description="是否检查系统所需的命令行程序是否可用。",
        ),
    ] = True
    log_monitor_active: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["log_monitor.active"],
            description="是否检查运行中服务器是否都有活动的日志监控任务。",
        ),
    ] = True
    server_backup_mod_removed: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["server.backup_mod_removed"],
            description="是否检查服务器 mods/plugins 目录中是否仍存在已知备份 Mod 或插件。",
        ),
    ] = True
    files_permission_consistency: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["files.permission_consistency"],
            description="是否检查服务器文件的所有者 UID 是否与服务器根目录一致。",
        ),
    ] = True
    server_filesystem_db_sync: Annotated[
        bool,
        Field(
            title=CHECK_LABELS["server.filesystem_db_sync"],
            description="是否检查文件系统中的服务器目录是否与数据库中的活动服务器记录一致。",
        ),
    ] = True

    def is_enabled(self, check_id: str) -> bool:
        field_name = self.CHECK_FIELD_BY_ID.get(check_id)
        return bool(field_name and getattr(self, field_name))

    def enabled_check_ids(self) -> set[str]:
        return {
            check_id
            for check_id in CHECK_IDS
            if self.is_enabled(check_id)
        }


class SelfCheckEventTriggerConfig(BaseConfigSchema):
    model_config = ConfigDict(title="事件触发自检配置")

    after_server_created: Annotated[
        bool,
        Field(title="创建服务器后自检", description="服务器创建完成后自动运行系统自检。"),
    ] = True
    after_server_populated: Annotated[
        bool,
        Field(title="填充服务器文件后自检", description="服务器文件填充完成后自动运行系统自检。"),
    ] = True
    after_world_restored: Annotated[
        bool,
        Field(title="恢复世界后自检", description="世界恢复完成后自动运行系统自检。"),
    ] = True
    after_world_rolled_back: Annotated[
        bool,
        Field(title="回档后自检", description="世界回档完成后自动运行系统自检。"),
    ] = True


class SelfCheckConfig(BaseConfigSchema):
    model_config = ConfigDict(title="系统自检配置")

    @model_validator(mode="before")
    @classmethod
    def _migrate_backup_mod_ids(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        migrated = dict(values)
        legacy_patterns = migrated.pop("backup_mod_name_patterns", None)
        if "backup_mod_ids" not in migrated and legacy_patterns:
            migrated["backup_mod_ids"] = default_backup_mod_ids()
        return migrated

    checks: Annotated[
        SelfCheckEnabledChecksConfig,
        Field(title="自检项开关", description="控制每一个系统自检项是否运行。"),
    ] = Field(default_factory=SelfCheckEnabledChecksConfig)
    snapshot_freshness_minutes: Annotated[
        int,
        Field(
            title="快照新鲜度上限",
            description="覆盖服务器的最新快照允许的最大年龄（分钟）。",
            ge=1,
        ),
    ] = 30
    backup_repository_usage_percent: Annotated[
        float,
        Field(
            title="备份仓库磁盘使用率阈值",
            description="Restic 备份仓库所在磁盘使用率达到该百分比时发出警告。",
            ge=1,
            le=100,
        ),
    ] = 85.0
    server_directory_usage_percent: Annotated[
        float,
        Field(
            title="服务器目录磁盘使用率阈值",
            description="服务器目录所在磁盘使用率达到该百分比时发出警告。",
            ge=1,
            le=100,
        ),
    ] = 85.0
    retention_runs_keep_days: Annotated[
        int,
        Field(title="自检历史保留天数", description="自检运行历史在数据库中保留的天数。", ge=1),
    ] = 14
    backup_mod_ids: Annotated[
        list[str],
        Field(
            title="备份 Mod/插件 ID",
            description="用于识别服务器内备份 Mod 或插件的 jar 元数据 ID，大小写不敏感。",
        ),
    ] = Field(default_factory=default_backup_mod_ids)
    permission_scan_max_entries: Annotated[
        int,
        Field(
            title="所有者扫描最大异常数",
            description="每台服务器最多记录的所有者 UID 异常文件数量。",
            ge=100,
        ),
    ] = 20000
    event_triggers: Annotated[
        SelfCheckEventTriggerConfig,
        Field(title="事件触发开关", description="控制哪些系统事件完成后自动运行自检。"),
    ] = SelfCheckEventTriggerConfig()

    def is_check_enabled(self, check_id: str) -> bool:
        return self.checks.is_enabled(check_id)

    def enabled_check_ids(self) -> set[str]:
        return self.checks.enabled_check_ids()

    @model_validator(mode="after")
    def _normalize_backup_mod_ids(self):
        self.backup_mod_ids = [
            normalized
            for mod_id in self.backup_mod_ids
            if (normalized := normalize_jar_id(mod_id)) is not None
        ]
        return self
