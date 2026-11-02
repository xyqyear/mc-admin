import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path

import aiofiles
import aiofiles.os as aioos
import yaml

from ..dynamic_config import get_config
from ..errors import log_safe_error
from ..files.utils import get_uid_gid
from ..logger import get_logger
from ..runtime_resources import current_runtime
from ..system.resources import get_disk_info
from ..utils import async_fs
from ..utils.exec import exec_command
from .compose import MCComposeFile, ServerType
from .docker.commands import (
    RCON_EXECUTION_TIMEOUT,
    RCON_TIMEOUT,
    ServerMissing,
    ServerUnavailable,
)
from .docker.compose_file import ComposeFile
from .docker.manager import ComposeManager
from .docker.reader import ContainerState, ProjectState, ProjectTarget
from .paths import (
    confined_server_file,
    find_compose_file,
    resolve_server_paths,
    validate_server_name,
)
from .properties import ServerProperties
from .status import MCServerStatus

ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass(frozen=True)
class MCServerInfo:
    name: str
    path: str | Path
    java_version: int
    max_memory_bytes: int
    server_type: ServerType
    game_version: str
    game_port: int
    rcon_port: int


@dataclass(frozen=True)
class DiskSpaceInfo:
    used_bytes: int
    total_bytes: int
    available_bytes: int

    @property
    def usage_percentage(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.used_bytes / self.total_bytes) * 100


class MCInstance:
    def __init__(self, servers_path: str | Path, name: str) -> None:
        validate_server_name(name)
        self._servers_path = Path(servers_path)
        self._name = name
        self._project_path = self._servers_path / self._name
        self._compose_manager = ComposeManager(self._project_path)

    def get_name(self) -> str:
        return self._name

    def get_project_path(self) -> Path:
        return self._project_path

    def get_compose_manager(self) -> ComposeManager:
        return self._compose_manager

    def get_data_path(self) -> Path:
        return self._project_path / "data"

    async def get_compose_file_path(self) -> Path | None:
        paths = await resolve_server_paths(self._servers_path, self._name)
        return await find_compose_file(paths)

    def _get_server_properties_path(self) -> Path:
        return self.get_data_path() / "server.properties"

    async def get_server_properties(self) -> ServerProperties:
        paths = await resolve_server_paths(self._servers_path, self._name)
        server_properties_path = self._get_server_properties_path()
        await confined_server_file(paths.data_path, server_properties_path)
        async with aiofiles.open(server_properties_path) as f:
            server_properties_content = await f.read()
        return ServerProperties.from_server_properties(server_properties_content)

    def _verify_compose_yaml(self, compose_yaml: str) -> bool:
        """Validate that the YAML parses as a Minecraft compose file matching ``self._name``."""
        try:
            compose_dict = yaml.load(compose_yaml, Loader=yaml.CLoader)
            compose_obj = ComposeFile.from_dict(compose_dict)
            mc_compose = MCComposeFile(compose_obj)
            if mc_compose.get_server_name() != self._name:
                raise ValueError(
                    "服务器名称与container_name不匹配, container_name应该为mc-服务器名"
                )
            return mc_compose.get_server_name() == self._name
        except Exception as exc:  # noqa: BLE001 - validation rejects input without exposing its values
            log_safe_error(exc, "Operation _verify_compose_yaml failed")
            return False

    async def get_compose_file(self) -> str:
        """Read the compose file as a YAML string. Raises ``FileNotFoundError`` if missing."""
        compose_file_path = await self.get_compose_file_path()
        if compose_file_path is None:
            raise FileNotFoundError(
                f"Could not find compose file for server {self._name}"
            )

        async with aiofiles.open(compose_file_path, "r", encoding="utf8") as file:
            return await file.read()

    async def get_compose_obj(self) -> MCComposeFile:
        compose_file_path = await self.get_compose_file_path()
        if compose_file_path is None:
            raise FileNotFoundError(
                f"Could not find compose file for server {self._name}"
            )
        compose_obj = await ComposeFile.async_from_file(compose_file_path)

        mc_compose = MCComposeFile(compose_obj)
        if mc_compose.get_server_name() != self._name:
            raise FileNotFoundError(
                f"Could not find valid compose file file for server {self._name}"
            )

        return mc_compose

    async def create(self, compose_yaml: str) -> None:
        """Write a new compose file plus an empty ``data/`` dir for this server."""
        await resolve_server_paths(self._servers_path, self._name)
        if not self._verify_compose_yaml(compose_yaml):
            raise ValueError(
                "Invalid compose YAML or doesn't meet Minecraft server requirements"
            )

        await aioos.makedirs(self._project_path, exist_ok=True)
        if await self.get_compose_file_path() is not None:
            raise FileExistsError(
                f"compose file already exists for server {self._name}"
            )

        compose_file_path = self._project_path / "docker-compose.yml"
        async with aiofiles.open(compose_file_path, "w", encoding="utf8") as file:
            await file.write(compose_yaml)

        await aioos.makedirs(self.get_data_path(), exist_ok=True)

        # Match the servers_path owner so the runtime container can read/write everything.
        uid, gid = await get_uid_gid(self._servers_path)
        if uid is not None and gid is not None:
            await async_fs.chown(self._project_path, uid, gid)
            await async_fs.chown(self.get_data_path(), uid, gid)
            await async_fs.chown(compose_file_path, uid, gid)

    async def remove(self) -> None:
        await self.get_compose_file_path()
        if await self.created():
            raise RuntimeError(f"Cannot remove server {self._name} while it is created")
        await async_fs.rmtree(self._project_path)

    async def up(self) -> None:
        await self.get_compose_file_path()
        await self._compose_manager.up_detached()

    async def down(self) -> None:
        await self.get_compose_file_path()
        await self._compose_manager.down()

    async def start(self) -> None:
        await self.get_compose_file_path()
        await self._compose_manager.start()

    async def stop(self) -> None:
        await self.get_compose_file_path()
        await self._compose_manager.stop()

    async def restart(self) -> None:
        await self.get_compose_file_path()
        await self._compose_manager.restart()

    async def exists(self) -> bool:
        """The server has a compose file."""
        compose_file_path = await self.get_compose_file_path()
        return compose_file_path is not None

    async def created(self) -> bool:
        return await self.get_status() not in {MCServerStatus.REMOVED, MCServerStatus.EXISTS}

    async def running(self) -> bool:
        return await self.get_status() in {MCServerStatus.RUNNING, MCServerStatus.STARTING, MCServerStatus.HEALTHY}

    async def starting(self) -> bool:
        return await self.get_status() == MCServerStatus.STARTING

    async def healthy(self) -> bool:
        return await self.get_status() == MCServerStatus.HEALTHY

    async def get_project_target(self) -> ProjectTarget:
        compose = await self.get_compose_obj()
        return ProjectTarget(self._project_path, compose.mc_service.container_name, compose.name)

    async def get_project_state(self) -> ProjectState:
        if not await self.exists():
            return ProjectState(MCServerStatus.REMOVED)
        return await current_runtime().docker_reader.observe(await self.get_project_target())

    async def get_status(self) -> MCServerStatus:
        """Highest reached lifecycle state; states are inclusive (HEALTHY implies RUNNING)."""
        return (await self.get_project_state()).status

    async def wait_until_healthy(self) -> None:
        if not await self.running():
            raise RuntimeError(f"Server {self._name} is not running")
        while not await self.healthy():
            await asyncio.sleep(0.5)

    async def get_disk_space_info(self) -> DiskSpaceInfo:
        """Used/total/available bytes for the server's data dir."""
        await resolve_server_paths(self._servers_path, self._name)
        if not await aioos.path.exists(self.get_data_path()):
            raise RuntimeError(f"Data directory does not exist for server {self._name}")

        du_result = await exec_command("du", "-sb", str(self.get_data_path()), timeout=60)
        used_bytes = int(du_result.split()[0])

        disk = await get_disk_info(self.get_data_path())

        return DiskSpaceInfo(
            used_bytes=used_bytes,
            total_bytes=disk.total,
            available_bytes=disk.available,
        )

    async def get_server_info(self):
        """Strongly-typed view of the server compose; ``MCComposeFile`` enforces validity."""
        mc_compose = await self.get_compose_obj()

        return MCServerInfo(
            name=mc_compose.get_server_name(),
            path=self._compose_manager.project_path,
            java_version=mc_compose.get_java_version(),
            max_memory_bytes=mc_compose.get_max_memory_bytes(),
            server_type=mc_compose.get_server_type(),
            game_version=mc_compose.get_game_version(),
            game_port=mc_compose.get_game_port(),
            rcon_port=mc_compose.get_rcon_port(),
        )

    async def list_players_query(self) -> list[str]:
        """Query the server's UDP query port for the player list."""
        return await self._query_players(await self.get_command_container())

    async def get_command_container(self) -> ContainerState:
        state = await self.get_project_state()
        if state.status == MCServerStatus.REMOVED:
            raise ServerMissing(f"服务器 '{self._name}' 不存在")
        if state.status != MCServerStatus.HEALTHY or state.container is None:
            raise ServerUnavailable("服务器当前无法执行命令（未在健康状态）")
        return state.container

    async def _query_players(self, container: ContainerState) -> list[str]:
        server_properties = await self.get_server_properties()

        if not server_properties.enable_query:
            raise RuntimeError("Query protocol is not enabled in server.properties")
        if not server_properties.query_port:
            raise RuntimeError("Query port is not configured in server.properties")

        query_command = get_config().players.query.query_command.replace(
            "25565", str(server_properties.query_port)
        )
        timeout = get_config().players.query.timeout

        result = await current_runtime().docker_commands.execute(
            container, ["bash", "-c", query_command],
            execution_timeout=timeout, timeout=timeout + 3.0, kind="query",
        )
        result = result.strip()
        if not result:
            return []

        return [player.strip() for player in result.split("\n") if player.strip()]

    async def _list_players_rcon(self, container: ContainerState) -> list[str]:
        players = await self._rcon(container, "list")
        if ":" not in players:
            return []
        players_str = players.split(":")[1].strip()
        return [
            player.strip() for player in players_str.split(",") if player.strip() != ""
        ]

    async def list_players(self) -> list[str]:
        """Try the query protocol first; fall back to RCON ``list``."""
        logger = get_logger()
        container = await self.get_command_container()
        try:
            return await self._query_players(container)
        except ServerUnavailable:
            raise
        except (RuntimeError, OSError, ValueError):
            logger.debug("Query failed for server %s; falling back to RCON", self._name)

        return await self._list_players_rcon(container)

    async def send_command_rcon(self, command: str) -> str:
        """Run ``command`` via the container's ``rcon-cli`` (provided by itzg/minecraft-server)."""
        started = time.monotonic()
        async with asyncio.timeout(RCON_TIMEOUT):
            container = await self.get_command_container()
            return await self._rcon(container, command, timeout=RCON_TIMEOUT - (time.monotonic() - started))

    async def _rcon(self, container: ContainerState, command: str, *, timeout: float = RCON_TIMEOUT) -> str:
        result = await current_runtime().docker_commands.execute(
            container, ["rcon-cli", command], execution_timeout=RCON_EXECUTION_TIMEOUT,
            timeout=timeout, kind="rcon",
        )
        return ANSI_ESCAPE_PATTERN.sub("", result).strip()

    async def get_container_id(self) -> str:
        state = await self.get_project_state()
        if state.container is None:
            raise RuntimeError("服务器容器尚未创建")
        return state.container.container_id
