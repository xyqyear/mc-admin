"""Self-check identifiers and trigger names."""

CHECK_IDS: tuple[str, ...] = (
    "backup.restic_configured",
    "backup.restic_reachable",
    "backup.server_snapshot_coverage",
    "backup.server_snapshot_freshness",
    "storage.backup_repository_usage",
    "storage.server_directory_usage",
    "locks.python_restic_active",
    "locks.repo_restic_active",
    "dns.drift",
    "dependency.binaries",
    "log_monitor.active",
    "server.backup_mod_removed",
    "files.permission_consistency",
    "server.filesystem_db_sync",
)

CHECK_LABELS: dict[str, str] = {
    "backup.restic_configured": "Restic 配置",
    "backup.restic_reachable": "Restic 仓库连通性",
    "backup.server_snapshot_coverage": "服务器快照覆盖",
    "backup.server_snapshot_freshness": "服务器快照新鲜度",
    "storage.backup_repository_usage": "备份仓库磁盘使用率",
    "storage.server_directory_usage": "服务器目录磁盘使用率",
    "locks.python_restic_active": "Python Restic 操作锁",
    "locks.repo_restic_active": "Restic 仓库锁",
    "dns.drift": "DNS 状态漂移",
    "dependency.binaries": "命令行依赖",
    "log_monitor.active": "日志监控状态",
    "server.backup_mod_removed": "备份 Mod 清理",
    "files.permission_consistency": "文件所有者一致性",
    "server.filesystem_db_sync": "文件系统与数据库同步",
}

MANUAL_TRIGGER = "manual"
SCHEDULED_TRIGGER = "scheduled"
SERVER_CREATED_TRIGGER = "server_created"
SERVER_POPULATED_TRIGGER = "server_populated"
WORLD_RESTORED_TRIGGER = "world_restored"
WORLD_ROLLED_BACK_TRIGGER = "world_rolled_back"
