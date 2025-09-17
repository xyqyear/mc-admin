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
        raise ValueError(f"服务器 '{params.server_id}' 未找到")
    
    if not await instance.running():
        context.log(f"服务器 '{params.server_id}' 未在运行中，跳过重启")
        return

    context.log(f"正在重启服务器: {params.server_id}")
    await instance.restart()
    context.log(f"服务器 '{params.server_id}' 重启完成")
