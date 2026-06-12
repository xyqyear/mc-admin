from datetime import timedelta

from ...config import settings
from ...minecraft import docker_mc_manager
from ...snapshots import snapshot_service
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, skipped, success


async def check_restic_configured(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["backup.restic_configured"]
    if settings.restic is None or snapshot_service is None:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="未配置 Restic，无法确认自动备份覆盖情况。",
                remediation=["在 config.toml 中添加 Restic 配置。"],
            )
        ]
    return success(definition, "Restic 配置已存在。")


async def check_restic_reachable(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["backup.restic_reachable"]
    if snapshot_service is None:
        return skipped(definition, "未配置 Restic。")

    snapshots, error = await context.snapshots()
    if error:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="无法查询 Restic 仓库。",
                evidence={"error": error},
                remediation=["检查 Restic 仓库路径、密码和可执行文件配置。"],
            )
        ]
    return success(definition, f"Restic 返回了 {len(snapshots or [])} 个快照。")


async def check_server_snapshot_coverage(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["backup.server_snapshot_coverage"]
    if snapshot_service is None:
        return skipped(definition, "未配置 Restic。")

    _, error = await context.snapshots()
    if error:
        return skipped(definition, "当前无法读取 Restic 快照。")

    active_servers = await context.active_servers()
    if not active_servers:
        return success(definition, "没有需要检查备份覆盖的运行中服务器。")

    findings: list[SelfCheckFindingResult] = []
    max_age = timedelta(minutes=context.config.snapshot_freshness_minutes)
    for server in active_servers:
        project_path = docker_mc_manager.get_instance(server.server_id).get_project_path()
        matching = await context.snapshots_covering(project_path)
        if matching:
            continue

        server_age = context.now - server.created_at
        if server_age <= max_age:
            findings.append(
                finding(
                    check_id=definition.check_id,
                    category=definition.category,
                    severity="info",
                    status="skipped",
                    title=definition.title,
                    message="服务器暂时没有覆盖它的快照，但仍在快照新鲜度上限内。",
                    server_id=server.server_id,
                    evidence={
                        "created_at": server.created_at.isoformat(),
                        "max_age_minutes": context.config.snapshot_freshness_minutes,
                    },
                )
            )
            continue

        findings.append(
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="服务器项目目录没有被任何 Restic 快照覆盖。",
                server_id=server.server_id,
                evidence={"path": str(project_path)},
                remediation=["为这台服务器运行一次备份快照。"],
            )
        )

    if not findings:
        return success(definition, "所有运行中的服务器都有快照覆盖。")
    return findings


async def check_server_snapshot_freshness(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["backup.server_snapshot_freshness"]
    if snapshot_service is None:
        return skipped(definition, "未配置 Restic。")

    _, error = await context.snapshots()
    if error:
        return skipped(definition, "当前无法读取 Restic 快照。")

    active_servers = await context.active_servers()
    if not active_servers:
        return success(definition, "没有需要检查快照新鲜度的运行中服务器。")

    findings: list[SelfCheckFindingResult] = []
    max_age = timedelta(minutes=context.config.snapshot_freshness_minutes)
    for server in active_servers:
        project_path = docker_mc_manager.get_instance(server.server_id).get_project_path()
        matching = await context.snapshots_covering(project_path)
        if not matching:
            if context.now - server.created_at <= max_age:
                findings.append(
                    finding(
                        check_id=definition.check_id,
                        category=definition.category,
                        severity="info",
                        status="skipped",
                        title=definition.title,
                        message="服务器暂时没有覆盖它的快照，但仍在快照新鲜度上限内。",
                        server_id=server.server_id,
                        evidence={
                            "created_at": server.created_at.isoformat(),
                            "max_age_minutes": context.config.snapshot_freshness_minutes,
                        },
                    )
                )
            continue

        newest = matching[0]
        age = context.now - newest.time
        if age > max_age:
            findings.append(
                finding(
                    check_id=definition.check_id,
                    category=definition.category,
                    severity="warning",
                    status="warning",
                    title=definition.title,
                    message="覆盖这台服务器的最新快照已超过配置的新鲜度上限。",
                    server_id=server.server_id,
                    evidence={
                        "snapshot_id": newest.short_id,
                        "snapshot_time": newest.time.isoformat(),
                        "max_age_minutes": context.config.snapshot_freshness_minutes,
                    },
                    remediation=["为这台服务器运行一次新的备份快照。"],
                )
            )

    if not findings:
        return success(definition, "所有已覆盖的服务器都有足够新的快照。")
    return findings


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "backup.restic_configured",
            "backup",
            "Restic 配置",
            "检查 Restic 相关配置是否可用。",
            check_restic_configured,
        ),
        CheckDefinition(
            "backup.restic_reachable",
            "backup",
            "Restic 仓库连通性",
            "检查是否可以查询 Restic 仓库。",
            check_restic_reachable,
        ),
        CheckDefinition(
            "backup.server_snapshot_coverage",
            "backup",
            "服务器快照覆盖",
            "检查每台运行中服务器是否至少被一个快照覆盖。",
            check_server_snapshot_coverage,
        ),
        CheckDefinition(
            "backup.server_snapshot_freshness",
            "backup",
            "服务器快照新鲜度",
            "检查已覆盖的服务器是否拥有足够新的快照。",
            check_server_snapshot_freshness,
        ),
    ]
}


_check_restic_configured = check_restic_configured
_check_restic_reachable = check_restic_reachable
_check_server_snapshot_coverage = check_server_snapshot_coverage
_check_server_snapshot_freshness = check_server_snapshot_freshness
