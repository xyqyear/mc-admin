from ...dns import simple_dns_manager
from ...dynamic_config import config
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, skipped, success


async def check_dns_drift(context: SelfCheckContext) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["dns.drift"]
    if not config.dns.enabled:
        return skipped(definition, "DNS 管理未启用。")

    try:
        dns_diff, router_diff = await simple_dns_manager.get_current_diff(context.db)
    except Exception as exc:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="无法计算 DNS 记录或 MC Router 路由的漂移情况。",
                evidence={"error": str(exc)},
                remediation=["检查 DNS 管理配置以及 DNS 提供商连接状态。"],
            )
        ]

    dns_count = (
        len(dns_diff.records_to_add)
        + len(dns_diff.records_to_remove)
        + len(dns_diff.records_to_update)
    )
    router_count = sum(len(router_diff[key]) for key in router_diff)
    if dns_count == 0 and router_count == 0:
        return success(definition, "DNS 记录和 MC Router 路由与目标状态一致。")

    return [
        finding(
            check_id=definition.check_id,
            category=definition.category,
            severity="warning",
            status="warning",
            title=definition.title,
            message="DNS 记录或 MC Router 路由与当前服务器状态不一致。",
            evidence={
                "dns_records_to_add": len(dns_diff.records_to_add),
                "dns_records_to_remove": len(dns_diff.records_to_remove),
                "dns_records_to_update": len(dns_diff.records_to_update),
                "router_routes_to_add": len(router_diff.get("routes_to_add", {})),
                "router_routes_to_remove": len(router_diff.get("routes_to_remove", {})),
                "router_routes_to_update": len(router_diff.get("routes_to_update", {})),
            },
            remediation=["运行 DNS 同步。"],
        )
    ]


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "dns.drift",
            "dns",
            "DNS 状态漂移",
            "检查 DNS 记录和 MC Router 路由是否与运行中服务器一致。",
            check_dns_drift,
        ),
    ]
}


_check_dns_drift = check_dns_drift
