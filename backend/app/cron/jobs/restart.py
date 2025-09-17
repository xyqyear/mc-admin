from typing import cast

from ...config import settings
from ...dynamic_config.schemas import BaseConfigSchema
from ...minecraft import DockerMCManager
from ..types import ExecutionContext

mc_manager = DockerMCManager(settings.server_path)


class ServerRestartParams(BaseConfigSchema):
    server_id: str


async def restart_server_cronjob(context: ExecutionContext):
    params = cast(ServerRestartParams, context.params)

    instance = mc_manager.get_instance(params.server_id)
    if not await instance.exists():
        context.log(f"服务器 '{params.server_id}' 未找到")
        raise ValueError(f"服务器 '{params.server_id}' 未找到")

    context.log(f"正在重启服务器: {params.server_id}")
    await instance.restart()
    context.log(f"服务器 '{params.server_id}' 重启完成")
