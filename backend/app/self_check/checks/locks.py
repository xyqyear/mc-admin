from ...snapshots import snapshot_service
from ...world import GLOBAL_LOCK_KEY, server_operation_lock
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, skipped, success


async def check_python_restic_active(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["locks.python_restic_active"]
    holders = server_operation_lock.get_holders()
    if not holders:
        return success(definition, "当前没有 Python 代码持有的 Restic 操作锁。")

    return [
        finding(
            check_id=definition.check_id,
            category=definition.category,
            severity="info",
            status="info",
            title=definition.title,
            message="当前存在 Python 代码持有的 Restic 操作锁。",
            server_id=None if key == GLOBAL_LOCK_KEY else key,
            evidence={
                "lock_key": key,
                "kind": holder.kind.value,
                "started_at": holder.started_at.isoformat(),
                "user_id": holder.user_id,
                "description": holder.description,
                "restoration_id": holder.restoration_id,
            },
        )
        for key, holder in sorted(holders.items())
    ]


async def check_repo_restic_active(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["locks.repo_restic_active"]
    if snapshot_service is None:
        return skipped(definition, "未配置 Restic。")

    try:
        output = await snapshot_service.list_locks()
    except Exception as exc:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="info",
                status="info",
                title=definition.title,
                message="无法查询 Restic 仓库锁。",
                evidence={"error": str(exc)},
            )
        ]

    normalized = output.strip()
    if not normalized or "no locks" in normalized.lower():
        return success(definition, "Restic 仓库未报告活动锁。")
    return [
        finding(
            check_id=definition.check_id,
            category=definition.category,
            severity="info",
            status="info",
            title=definition.title,
            message="Restic 仓库报告存在活动锁条目。",
            evidence={"output": normalized[:4000]},
        )
    ]


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "locks.python_restic_active",
            "locks",
            "Python Restic 操作锁",
            "展示 Python 代码中当前活动的备份或恢复锁。",
            check_python_restic_active,
        ),
        CheckDefinition(
            "locks.repo_restic_active",
            "locks",
            "Restic 仓库锁",
            "展示 Restic 仓库内部当前活动的锁条目。",
            check_repo_restic_active,
        ),
    ]
}


_check_python_restic_active = check_python_restic_active
_check_repo_restic_active = check_repo_restic_active
