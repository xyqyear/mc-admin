import asyncio
from pathlib import Path

from aiofiles import os as aioos

from .compose import MCComposeFile
from .docker.manager import DockerManager
from .instance import MCInstance, MCServerInfo


class DockerMCManager:
    def __init__(self, servers_path: str | Path) -> None:
        self.servers_path = Path(servers_path)

    async def get_all_server_compose_obj(self) -> list[MCComposeFile]:
        compose_obj_list = list[MCComposeFile]()
        for sub_dir in await aioos.listdir(self.servers_path):
            instance = self.get_instance(sub_dir)
            try:
                compose_obj_list.append(await instance.get_compose_obj())
            except FileNotFoundError:
                continue
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

    async def get_all_server_compose_paths(self) -> list[Path]:
        instances = await self.get_all_instances()
        compose_path_coroutine_list = [
            instance.get_compose_file_path() for instance in instances
        ]
        return [
            compose_path
            for compose_path in await asyncio.gather(*compose_path_coroutine_list)
            if compose_path is not None
        ]

    async def get_all_server_info(self) -> list[MCServerInfo]:
        instances = await self.get_all_instances()
        server_info_coroutine_list = [
            instance.get_server_info() for instance in instances
        ]
        return await asyncio.gather(*server_info_coroutine_list)

    async def get_running_server_names(self):
        """
        uses docker api to get all running servers (docker compose ps)
        """
        container_list = await DockerManager.ps()
        server_names = await self.get_all_server_names()
        running_servers = list[str]()
        for container in container_list:
            if not container.names.startswith("mc-"):
                continue
            potential_server_name = container.names[3:]
            if potential_server_name not in server_names:
                continue

            compose_file_path = container.labels[
                "com.docker.compose.project.config_files"
            ]

            if not await aioos.path.samefile(
                Path(compose_file_path).parent.parent, self.servers_path
            ):
                continue

            running_servers.append(potential_server_name)
        return running_servers

    def get_instance(self, server_name: str) -> MCInstance:
        return MCInstance(self.servers_path, server_name)
