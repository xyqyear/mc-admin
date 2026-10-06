from pathlib import Path

from aiofiles import os as aioos

from ..logger import get_logger
from ..runtime_resources import current_runtime
from .compose import MCComposeFile
from .instance import MCInstance
from .paths import ServerPathError


class DockerMCManager:
    def __init__(self, servers_path: str | Path) -> None:
        self.servers_path = Path(servers_path).resolve()

    async def get_all_server_compose_obj(self) -> list[MCComposeFile]:
        logger = get_logger()
        compose_obj_list = list[MCComposeFile]()
        for sub_dir in await aioos.listdir(self.servers_path):
            try:
                instance = self.get_instance(sub_dir)
                compose_obj_list.append(await instance.get_compose_obj())
            except FileNotFoundError:
                continue
            # 验证失败则忽略
            except ValueError:
                continue
            except ServerPathError:
                logger.warning("Skipped server directory with an invalid path boundary")
                continue
            except Exception as e:
                logger.warning(f"Failed to get compose object for {sub_dir}: {e}", exc_info=True)
        return compose_obj_list

    async def get_all_server_names(self) -> list[str]:
        """
        iterate through all the subdirectories and filter out the ones that looks like a minecraft server
        """
        compose_obj_list = await self.get_all_server_compose_obj()
        return [mc_compose.get_server_name() for mc_compose in compose_obj_list]

    async def get_all_instances(self) -> list[MCInstance]:
        return [
            self.get_instance(server_name)
            for server_name in await self.get_all_server_names()
        ]

    def get_instance(self, server_name: str) -> MCInstance:
        return MCInstance(self.servers_path, server_name)


# Singleton instance
def get_docker_mc_manager() -> DockerMCManager:
    return current_runtime().docker_mc_manager
