import httpx2
from huaweicloudsdkcore.exceptions.exceptions import SdkException
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from ...errors import public_error_message
from ...logger import get_logger
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, skipped, success


async def check_dns_drift(context: SelfCheckContext) -> list[SelfCheckFindingResult]:
    logger = get_logger()
    definition = DEFINITIONS["dns.drift"]
    if not context.dependencies.configuration.dns.enabled:
        return skipped(definition, "DNS 管理未启用。")

    try:
        observation = await context.dependencies.connectivity.observe(context.db)
    except (
        SdkException,
        TencentCloudSDKException,
        httpx2.HTTPError,
        ValueError,
        RuntimeError,
        OSError,
    ) as exc:
        logger.warning("Cannot calculate DNS drift (%s)", type(exc).__name__)
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="无法计算 DNS 记录或 MC Router 路由的漂移情况。",
                evidence={"error": public_error_message(exc)},
                remediation=["检查 DNS 管理配置以及 DNS 提供商连接状态。"],
            )
        ]

    if observation.state == "degraded":
        return [finding(
            check_id=definition.check_id, category=definition.category,
            severity="warning", status="warning", title=definition.title,
            message="部分连接状态无法确认，请修复后重新同步。",
            evidence={
                "dns_known": observation.dns_known,
                "router_known": observation.router_known,
                "unknown_servers": list(observation.unknown_servers),
                "issues": list(observation.issues),
            },
            remediation=["检查 DNS 服务商、MC Router 和服务器配置后重新同步。"],
        )]
    if observation.empty_desired:
        return skipped(definition, "当前没有可同步的地址或服务器，保留现有连接记录。")
    dns_diff = observation.dns_diff
    router_diff = observation.router_diff
    assert dns_diff is not None and router_diff is not None
    dns_count = (
        len(dns_diff.records_to_add)
        + len(dns_diff.records_to_remove)
        + len(dns_diff.records_to_update)
    )
    router_changes = router_diff.as_dict()
    router_count = sum(len(value) for value in router_changes.values())
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
                "router_routes_to_add": len(router_diff.routes_to_add),
                "router_routes_to_remove": len(router_diff.routes_to_remove),
                "router_routes_to_update": len(router_diff.routes_to_update),
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
