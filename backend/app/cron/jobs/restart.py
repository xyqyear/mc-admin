from typing import Annotated, cast

from pydantic import ConfigDict, Field

from ...dynamic_config.schemas import BaseConfigSchema
from ...servers.commands import ServerCommands
from ..types import ExecutionContext


class ServerRestartParams(BaseConfigSchema):
    """服务器重启任务参数。"""

    model_config = ConfigDict(title="服务器重启任务参数")

    server_id: Annotated[
        str,
        Field(title="服务器 ID", description="要重启的服务器 ID。"),
    ]


async def restart_server_cronjob(context: ExecutionContext):
    params = cast(ServerRestartParams, context.params)
    context.log(f"正在检查定时重启: {params.server_id}")
    result = await ServerCommands().execute(
        params.server_id, "restart", only_if_running=True,
        expected_generation=context.managed_server_generation,
    )
    if result.skipped:
        context.skip(result.reason or "服务器未满足重启条件，跳过重启")
        return
    context.log(f"服务器 '{params.server_id}' 重启完成")
