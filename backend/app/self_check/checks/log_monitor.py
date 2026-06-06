from ...log_monitor import log_monitor
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, success


async def check_log_monitor_active(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["log_monitor.active"]
    active_servers = await context.active_servers()
    if not active_servers:
        return success(definition, "没有需要日志监控的运行中服务器。")

    missing = [
        server.server_id
        for server in active_servers
        if not log_monitor.is_watching(server.server_id)
    ]
    if missing:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="部分运行中服务器没有活动的日志监控任务。",
                evidence={"servers": missing},
                remediation=["重启受影响的服务器，或重启 MC Admin。"],
            )
        ]
    return success(definition, "所有运行中服务器都有活动的日志监控任务。")


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "log_monitor.active",
            "log_monitor",
            "日志监控状态",
            "检查运行中服务器是否都有活动的日志监控任务。",
            check_log_monitor_active,
        ),
    ]
}


_check_log_monitor_active = check_log_monitor_active
