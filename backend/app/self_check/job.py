"""Cron entry point for automatic self-check runs."""

from typing import Annotated

from pydantic import ConfigDict, Field

from ..dynamic_config.schemas import BaseConfigSchema
from .constants import SCHEDULED_TRIGGER


RUN_STATUS_LABELS = {
    "success": "正常",
    "warning": "警告",
    "critical": "严重",
}


class SelfCheckJobParams(BaseConfigSchema):
    model_config = ConfigDict(title="系统自检任务参数")

    scope: Annotated[
        str,
        Field(
            title="检查范围",
            description="自动自检任务的检查范围；当前固定为全局自检。",
        ),
    ] = "global"


async def self_check_cronjob(context) -> None:
    from .runner import run_self_check

    result = await run_self_check(trigger=SCHEDULED_TRIGGER)
    status_label = RUN_STATUS_LABELS.get(result.status, result.status)
    context.log(
        "系统自检完成: "
        f"状态={status_label}, 警告={result.summary.warning}, "
        f"严重={result.summary.critical}, 运行ID={result.id}"
    )
