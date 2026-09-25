"""Managed schedules retain an incarnation independently of their display name."""

import json

from pydantic import ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.cron.models import CronJob
from app.servers.models import Server, ServerStatus

from ..dynamic_config.schemas import BaseConfigSchema

RESTART_PURPOSE = "restart"

BINDING_ISSUES = {
    "duplicate_candidates": "存在多个历史受管计划，无法确定唯一归属",
    "invalid_params": "历史任务参数无效，无法确定归属",
    "name_params_mismatch": "历史计划名称与服务器参数不一致",
    "server_missing": "历史计划没有可核对的服务器登记记录",
    "generation_uncertain": "历史计划的时间证据无法确定服务器实例代次",
}


def binding_issue_message(issue: str) -> str:
    return BINDING_ISSUES.get(issue, "历史计划归属不明确")


async def managed_binding_problem(session: AsyncSession, job: CronJob) -> str | None:
    if job.managed_purpose is None:
        return None
    if job.managed_binding_issue:
        return binding_issue_message(job.managed_binding_issue)
    server = await session.get(Server, job.managed_server_generation)
    if server is None or server.status != ServerStatus.ACTIVE:
        return "计划绑定的服务器实例已停用，不能应用到同名新实例"
    try:
        params = json.loads(job.params_json)
    except (TypeError, ValueError):
        return "受管计划参数无效，不能执行"
    if (
        job.managed_purpose != RESTART_PURPOSE
        or job.identifier != "restart_server"
        or not isinstance(params, dict)
        or params.get("server_id") != server.server_id
    ):
        return "受管计划参数与绑定的服务器实例不一致，不能执行"
    return None


async def validate_managed_update(
    session: AsyncSession, job: CronJob, identifier: str, params: BaseConfigSchema,
) -> None:
    if job.managed_purpose is None:
        return
    problem = await managed_binding_problem(session, job)
    if problem:
        raise ValueError(f"{problem}；请核对后取消该计划，并在服务器页面重新创建")
    server = await session.get(Server, job.managed_server_generation)
    if identifier != "restart_server" or server is None or getattr(params, "server_id", None) != server.server_id:
        raise ValueError("受管重启计划不能修改任务类型或服务器归属；请另建独立定时任务")


class RetainedCronParams(BaseConfigSchema):
    model_config = ConfigDict(extra="allow")


def read_cron_params(job: CronJob, schema: type[BaseConfigSchema]) -> BaseConfigSchema:
    try:
        return schema.model_validate_json(job.params_json)
    except (ValueError, TypeError):
        if not job.managed_binding_issue:
            raise
        try:
            raw = json.loads(job.params_json)
        except (ValueError, TypeError):
            raw = None
        return RetainedCronParams.model_validate(raw if isinstance(raw, dict) else {})
