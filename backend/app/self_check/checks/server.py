import asyncio
from dataclasses import dataclass
from pathlib import Path

import aiofiles

from ...minecraft import MCServerStatus, docker_mc_manager
from ...minecraft.game_port import get_game_port_mapping, get_properties_game_port
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


async def check_game_port_consistency(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["server.game_port_consistency"]
    servers = await context.active_servers()
    if not servers:
        return success(definition, "没有需要检查游戏端口的服务器。")

    findings: list[SelfCheckFindingResult] = []
    for server in servers:
        evidence = {}
        remediation = []
        stage = "status"
        try:
            instance = docker_mc_manager.get_instance(server.server_id)
            status = await instance.get_status()
            if status == MCServerStatus.STARTING:
                severity, finding_status = "info", "skipped"
                message = "服务器正在启动，暂时跳过端口比较，请稍后重新检测。"
            else:
                stage = "properties"
                properties_path = instance.get_data_path() / "server.properties"
                evidence["properties_path"] = str(properties_path)
                try:
                    async with aiofiles.open(properties_path, encoding="utf-8") as file:
                        content = await file.read()
                except FileNotFoundError:
                    if status in (MCServerStatus.RUNNING, MCServerStatus.HEALTHY):
                        raise
                    content = None

                if content is None:
                    severity, finding_status = "info", "skipped"
                    message = "server.properties 尚未生成，已跳过端口比较。"
                else:
                    properties_port = get_properties_game_port(content)
                    evidence["properties_server_port"] = properties_port
                    stage = "compose"
                    mapping = get_game_port_mapping(await instance.get_compose_file())
                    evidence["expected_container_port"] = mapping.target
                    evidence["published_game_port"] = mapping.published
                    if properties_port == mapping.target:
                        severity, finding_status = "success", "passed"
                        message = "server.properties 的游戏端口与 Compose 容器目标端口一致。"
                    else:
                        severity, finding_status = "warning", "warning"
                        message = (
                            f"server.properties 的游戏端口为 {properties_port}，"
                            f"与 Compose 容器目标端口 {mapping.target} 不一致。"
                        )
                        remediation = [
                            f"将 server.properties 中的 server-port 设置为 {mapping.target}，保存后重启服务器。",
                            "如果 Compose 显式设置了不同的 SERVER_PORT，启动时可能再次覆盖文件；"
                            "请修改 Compose 并重建容器，普通重启不会应用新的环境变量。",
                        ]
        except Exception as exc:
            severity, finding_status = "warning", "failed"
            evidence["error_stage"] = stage
            evidence["error_type"] = type(exc).__name__
            message = {
                "status": "无法获取服务器状态，未能检查游戏端口。",
                "properties": "无法读取有效的 server.properties 游戏端口，请检查文件及 server-port 值。",
                "compose": "无法读取 Compose 的 TCP 游戏容器目标端口，请检查映射配置。",
            }[stage]
            remediation = [message]

        findings.append(finding(
            check_id=definition.check_id,
            category=definition.category,
            severity=severity,
            status=finding_status,
            title=definition.title,
            message=message,
            server_id=server.server_id,
            evidence=evidence,
            remediation=remediation,
        ))
    return findings


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "server.game_port_consistency",
            "server",
            "游戏端口一致性",
            "比较 server.properties 的游戏端口与 Compose 容器目标端口，不检查网络连通性。",
            check_game_port_consistency,
        ),
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
