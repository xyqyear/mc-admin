from pathlib import Path

from ...config import settings
from ...system.resources import get_disk_info
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, skipped, success, usage_percent


async def check_backup_repository_usage(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["storage.backup_repository_usage"]
    if settings.restic is None:
        return skipped(definition, "未配置 Restic。")

    repository_path = Path(settings.restic.repository_path)
    try:
        disk = await get_disk_info(repository_path)
    except Exception as exc:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="无法读取备份仓库所在磁盘的使用情况。",
                evidence={"path": str(repository_path), "error": str(exc)},
            )
        ]

    percent = usage_percent(disk.used, disk.total)
    evidence = {
        "path": str(repository_path),
        "used_bytes": int(disk.used),
        "total_bytes": int(disk.total),
        "usage_percent": percent,
        "threshold_percent": context.config.backup_repository_usage_percent,
    }
    if percent >= context.config.backup_repository_usage_percent:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="备份仓库所在磁盘的使用率已超过配置阈值。",
                evidence=evidence,
                remediation=["清理磁盘空间，或将 Restic 仓库迁移到空间更充足的位置。"],
            )
        ]
    return success(definition, "备份仓库所在磁盘的使用率低于阈值。")


async def check_server_directory_usage(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["storage.server_directory_usage"]
    try:
        disk = await get_disk_info(settings.server_path)
    except Exception as exc:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="无法读取服务器目录所在磁盘的使用情况。",
                evidence={"path": str(settings.server_path), "error": str(exc)},
            )
        ]

    percent = usage_percent(disk.used, disk.total)
    evidence = {
        "path": str(settings.server_path),
        "used_bytes": int(disk.used),
        "total_bytes": int(disk.total),
        "usage_percent": percent,
        "threshold_percent": context.config.server_directory_usage_percent,
    }
    if percent >= context.config.server_directory_usage_percent:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="服务器目录所在磁盘的使用率已超过配置阈值。",
                evidence=evidence,
                remediation=["清理磁盘空间，或将服务器目录迁移到空间更充足的位置。"],
            )
        ]
    return success(definition, "服务器目录所在磁盘的使用率低于阈值。")


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "storage.backup_repository_usage",
            "storage",
            "备份仓库磁盘使用率",
            "检查 Restic 备份仓库所在文件系统的磁盘使用情况。",
            check_backup_repository_usage,
        ),
        CheckDefinition(
            "storage.server_directory_usage",
            "storage",
            "服务器目录磁盘使用率",
            "检查服务器目录所在文件系统的磁盘使用情况。",
            check_server_directory_usage,
        ),
    ]
}


_check_backup_repository_usage = check_backup_repository_usage
_check_server_directory_usage = check_server_directory_usage
