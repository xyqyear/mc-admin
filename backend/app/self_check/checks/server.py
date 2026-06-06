import asyncio
from dataclasses import dataclass
from pathlib import Path

from ...minecraft import docker_mc_manager
from ..jar_metadata import extract_jar_metadata, normalize_jar_id
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, success


@dataclass(frozen=True)
class BackupJarMatch:
    directory: str
    file: str
    ids: list[str]
    sources: list[str]


def find_backup_jars_sync(
    data_path: Path,
    configured_ids: list[str],
) -> list[BackupJarMatch]:
    target_ids = {
        normalized
        for configured_id in configured_ids
        if (normalized := normalize_jar_id(configured_id)) is not None
    }
    if not target_ids:
        return []

    matches: list[BackupJarMatch] = []
    for directory_name in ("mods", "plugins"):
        directory = data_path / directory_name
        if not directory.exists():
            continue
        for entry in directory.iterdir():
            if not entry.is_file() or entry.suffix.lower() != ".jar":
                continue

            metadata = extract_jar_metadata(entry)
            matched_ids = [mod_id for mod_id in metadata.ids if mod_id in target_ids]
            if matched_ids:
                matches.append(
                    BackupJarMatch(
                        directory=directory_name,
                        file=entry.name,
                        ids=matched_ids,
                        sources=list(metadata.sources),
                    )
                )
    return matches


async def check_backup_mod_removed(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["server.backup_mod_removed"]
    active_servers = await context.active_servers()
    if not active_servers:
        return success(definition, "没有需要检查备份 Mod 的运行中服务器。")

    findings: list[SelfCheckFindingResult] = []
    for server in active_servers:
        data_path = docker_mc_manager.get_instance(server.server_id).get_data_path()
        matches = await asyncio.to_thread(
            find_backup_jars_sync,
            data_path,
            context.config.backup_mod_ids,
        )
        if matches:
            findings.append(
                finding(
                    check_id=definition.check_id,
                    category=definition.category,
                    severity="warning",
                    status="warning",
                    title=definition.title,
                    message="服务器 mods/plugins 目录中仍存在备份 Mod 或插件。",
                    server_id=server.server_id,
                    evidence={
                        "data_path": str(data_path),
                        "jars": [
                            {
                                "directory": match.directory,
                                "file": match.file,
                                "ids": match.ids,
                                "sources": match.sources,
                            }
                            for match in matches[:20]
                        ],
                    },
                    remediation=["从服务器 mods/plugins 目录中移除这些备份 Mod 或插件。"],
                )
            )

    if not findings:
        return success(definition, "未发现匹配配置 ID 的备份 Mod 或插件。")
    return findings


async def check_filesystem_db_sync(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    from ...servers.lifecycle import preview_deactivation, validate_adoption

    definition = DEFINITIONS["server.filesystem_db_sync"]
    fs_set = await context.filesystem_servers()
    active_servers = await context.active_servers()
    active_set = {server.server_id for server in active_servers}

    fs_only = sorted(fs_set - active_set)
    db_only = sorted(active_set - fs_set)
    if not fs_only and not db_only:
        return success(definition, "文件系统中的服务器列表与数据库中的活动服务器记录一致。")

    adoption_errors: list[dict[str, str]] = []
    for server_id in fs_only:
        try:
            await validate_adoption(context.db, server_id)
        except Exception as exc:
            adoption_errors.append({"server_id": server_id, "error": str(exc)})

    deactivation_preview: list[dict[str, object]] = []
    for server_id in db_only:
        try:
            jobs, sessions = await preview_deactivation(context.db, server_id)
            deactivation_preview.append(
                {
                    "server_id": server_id,
                    "restart_cronjob_count": jobs,
                    "open_session_count": sessions,
                }
            )
        except Exception as exc:
            deactivation_preview.append({"server_id": server_id, "error": str(exc)})

    return [
        finding(
            check_id=definition.check_id,
            category=definition.category,
            severity="warning",
            status="warning",
            title=definition.title,
            message="文件系统中的服务器目录与数据库中的活动服务器记录不一致。",
            evidence={
                "filesystem_only": fs_only,
                "database_only": db_only,
                "adoption_errors": adoption_errors,
                "deactivation_preview": deactivation_preview,
            },
            remediation=["检查差异并运行服务器同步。"],
        )
    ]


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "server.backup_mod_removed",
            "server",
            "备份 Mod 清理",
            "检查服务器 mods/plugins 目录中是否仍存在已知备份 Mod 或插件。",
            check_backup_mod_removed,
        ),
        CheckDefinition(
            "server.filesystem_db_sync",
            "server",
            "文件系统与数据库同步",
            "检查文件系统中的服务器目录是否与数据库中的活动服务器记录一致。",
            check_filesystem_db_sync,
        ),
    ]
}


_find_backup_jars_sync = find_backup_jars_sync
_check_backup_mod_removed = check_backup_mod_removed
_check_filesystem_db_sync = check_filesystem_db_sync
