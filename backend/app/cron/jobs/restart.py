from typing import Annotated, cast

from pydantic import ConfigDict, Field

from ...dynamic_config.schemas import BaseConfigSchema
from ...minecraft import docker_mc_manager
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

    instance = docker_mc_manager.get_instance(params.server_id)
    if not await instance.exists():
        raise ValueError(f"服务器 '{params.server_id}' 未找到")

    if not await instance.running():
        context.log(f"服务器 '{params.server_id}' 未在运行中，跳过重启")
        return

    context.log(f"正在重启服务器: {params.server_id}")
    await instance.restart()
    context.log(f"服务器 '{params.server_id}' 重启完成")
