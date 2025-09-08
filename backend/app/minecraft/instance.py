import asyncio
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import aiofiles
import aiofiles.os as aioos
import yaml

from ..common.file_operations import _chown_async, get_uid_gid
from .compose import MCComposeFile, ServerType
from .docker.cgroup import (
    BlockIOStats,
    MemoryStats,
    read_block_io_stats,
    read_memory_stats,
)
from .docker.compose_file import ComposeFile
from .docker.manager import ComposeManager
from .docker.network import NetworkStats, read_container_network_stats
from .utils import async_rmtree, exec_command, get_process_cpu_usage

PLAYER_MESSAGE_PATTERN = re.compile(
    r"\]: (?:\[Not Secure\] )?<(?P<player>.*?)> (?P<message>.*)"
)
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class MCServerStatus(str, Enum):
    """Minecraft server status levels in hierarchical order"""

    REMOVED = "REMOVED"  # Server directory/config doesn't exist
    EXISTS = "EXISTS"  # Server config exists but container not created
    CREATED = "CREATED"  # Container created but not running
    RUNNING = "RUNNING"  # Container is running but may not be healthy
    STARTING = "STARTING"  # Container is starting
    HEALTHY = "HEALTHY"  # Container is running and healthy


@dataclass
class LogType:
    content: str
    pointer: int


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
class MCServerRunningInfo:
    cpu_percentage: float
    memory_usage_bytes: int
    disk_read_bytes: int
    disk_write_bytes: int
    network_receive_bytes: int
    network_send_bytes: int
    disk_usage_bytes: int
    disk_total_bytes: int
    disk_available_bytes: int

    @property
    def disk_usage_percentage(self) -> float:
        """Calculate disk usage percentage"""
        if self.disk_total_bytes == 0:
            return 0.0
        return (self.disk_usage_bytes / self.disk_total_bytes) * 100


@dataclass(frozen=True)
class DiskSpaceInfo:
    """Disk space information for server data directory"""

    used_bytes: int
    total_bytes: int
    available_bytes: int

    @property
    def usage_percentage(self) -> float:
        """Calculate disk usage percentage"""
        if self.total_bytes == 0:
            return 0.0
        return (self.used_bytes / self.total_bytes) * 100


@dataclass
class MCPlayerMessage:
    player: str
    message: str


class MCInstance:
    def __init__(self, servers_path: str | Path, name: str) -> None:
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

    async def get_compose_file_path(self) -> Path | None:
        candidates = [
            self._project_path / "docker-compose.yml",
            self._project_path / "docker-compose.yaml",
            self._project_path / "compose.yml",
            self._project_path / "compose.yaml",
        ]

        existence_checks = await asyncio.gather(
            *[aioos.path.exists(path) for path in candidates], return_exceptions=True
        )

        for path, exists in zip(candidates, existence_checks):
            if exists is True:
                return path

        return None

    def _verify_compose_yaml(self, compose_yaml: str) -> bool:
        """
        验证YAML字符串是否符合Minecraft服务器要求

        将YAML字符串转换为MCComposeFile对象并验证。
        """
        try:
            compose_dict = yaml.load(compose_yaml, Loader=yaml.CLoader)
            compose_obj = ComposeFile.from_dict(compose_dict)
            # MCComposeFile初始化成功 = 格式验证通过
            mc_compose = MCComposeFile(compose_obj)
            if mc_compose.get_server_name() != self._name:
                raise ValueError(
                    "服务器名称与container_name不匹配, container_name应该为mc-服务器名"
                )
            return mc_compose.get_server_name() == self._name
        except (yaml.YAMLError, ValueError, Exception):
            return False

    async def get_compose_file(self) -> str:
        """
        Get the current compose file content as a YAML string

        Returns:
            str: The current compose file content

        Raises:
            FileNotFoundError: If compose doesn't exist for this server
        """
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

        # Validate using MCComposeFile
        mc_compose = MCComposeFile(compose_obj)
        if mc_compose.get_server_name() != self._name:
            raise FileNotFoundError(
                f"Could not find valid compose file file for server {self._name}"
            )

        return mc_compose

    async def _get_log_path(self) -> Path:
        container_id = await self.get_container_id()
        return Path(
            f"/var/lib/docker/containers/{container_id}/{container_id}-json.log"
        )

    async def get_log_file_end_pointer(self) -> int:
        log_path = await self._get_log_path()
        async with aiofiles.open(log_path, mode="r", encoding="utf8") as f:
            await f.seek(0, 2)
            return await f.tell()

    def _parse_docker_json_log_line(self, line: str) -> str:
        """Parse a single Docker JSON log line and return the log content."""
        try:
            log_entry = json.loads(line.strip())
            return log_entry.get("log", "")
        except (json.JSONDecodeError, KeyError):
            # If parsing fails, return the original line
            return line

    async def get_logs_from_file(self, start: int = 0) -> LogType:
        """
        if start is negative, it will read start bytes from the end of the file
        if start is positive and no greater than the file size, it will read start bytes from the specified position
        if start is greater than the file size, it will read from the beginning of the file
        raises:
            FileNotFoundError: if the log file does not exist
        """
        log_path = await self._get_log_path()
        async with aiofiles.open(log_path, mode="r", encoding="utf8") as f:
            await f.seek(0, 2)
            file_size = await f.tell()
            if start < 0:
                start = file_size + start
                if start < 0:
                    start = 0
            elif start > file_size:
                start = 0
            await f.seek(start)
            raw_log = await f.read()

            # Parse Docker JSON log format
            parsed_lines = []
            for line in raw_log.splitlines(keepends=True):
                if line.strip():
                    parsed_content = self._parse_docker_json_log_line(line)
                    parsed_lines.append(parsed_content)

            log = "".join(parsed_lines)
            return LogType(content=log, pointer=await f.tell())

    @staticmethod
    def parse_player_messages_from_log(log: str) -> list[MCPlayerMessage]:
        return [
            MCPlayerMessage(
                player=match.group("player"), message=match.group("message").strip()
            )
            for match in PLAYER_MESSAGE_PATTERN.finditer(log)
        ]

    async def get_player_messages_from_log(
        self, start: int = 0
    ) -> tuple[list[MCPlayerMessage], int]:
        log = await self.get_logs_from_file(start)
        return self.parse_player_messages_from_log(log.content), log.pointer

    async def get_logs_from_docker(self, tail: int = 1000) -> str:
        return await self._compose_manager.logs(tail)

    @staticmethod
    def filter_rcon_logs(content: str) -> str:
        """
        Filter out RCON-related log lines from log content.

        Args:
            content: Raw log content

        Returns:
            Log content with RCON lines removed (empty lines are also removed for cleaner output)
        """
        if not content:
            return content

        lines = content.split("\n")
        filtered_lines = []

        for line in lines:
            # Filter out RCON Client and RCON Listener log lines
            if "[RCON Client" not in line and "[RCON Listener" not in line:
                filtered_lines.append(line)

        # Join and then split again to remove any empty lines that result from filtering
        result = "\n".join(filtered_lines)
        # Remove any sequences of multiple newlines, keeping only single newlines
        import re

        result = re.sub(r"\n\s*\n", "\n", result)
        return result

    async def get_logs_from_file_filtered(
        self, start: int = 0, filter_rcon: bool = True, max_chars: int = 1024 * 1024
    ) -> LogType:
        """
        Get logs from file with optional RCON filtering and 1M character limit.

        Args:
            start: Starting position for reading logs
            filter_rcon: Whether to filter out RCON-related logs
            max_chars: Maximum number of characters to return

        Returns:
            LogType with filtered content, truncated to 1M characters if needed
        """
        # Get the raw logs first
        raw_logs = await self.get_logs_from_file(start)
        content = raw_logs.content

        # Apply RCON filtering if requested
        if filter_rcon:
            content = self.filter_rcon_logs(content)

        if len(content) > max_chars:
            # Truncate from the end (keep the most recent logs)
            content = content[-max_chars:]

        return LogType(content=content, pointer=raw_logs.pointer)

    async def create(self, compose_yaml: str) -> None:
        """
        create a new directory for the server and write the compose file to it
        it also creates a data directory for the server

        Args:
            compose_yaml: Docker compose configuration as YAML string

        Raises:
            ValueError: If YAML is invalid or doesn't meet Minecraft server requirements
            FileExistsError: If compose file already exists for this server
        """
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

        # Set ownership to match the servers_path directory
        uid, gid = await get_uid_gid(self._servers_path)
        if uid is not None and gid is not None:
            await _chown_async(compose_file_path, uid, gid)

        await aioos.makedirs(self._project_path / "data", exist_ok=True)

    async def update_compose_file(self, compose_yaml: str) -> None:
        """
        Update the compose file for the server with a new YAML configuration

        Args:
            compose_yaml: Docker compose configuration as YAML string

        Raises:
            RuntimeError: If server is currently created/running
            ValueError: If YAML is invalid or doesn't meet Minecraft server requirements
            FileNotFoundError: If compose file doesn't exist for this server
        """
        if await self.created():
            raise RuntimeError(f"Cannot update server {self._name} while it is created")
        if not self._verify_compose_yaml(compose_yaml):
            raise ValueError(
                "Invalid compose YAML or doesn't meet Minecraft server requirements"
            )

        compose_file_path = await self.get_compose_file_path()
        if compose_file_path is None:
            raise FileNotFoundError(
                f"Could not find compose file for server {self._name}"
            )

        # Write YAML string directly to file
        async with aiofiles.open(compose_file_path, "w", encoding="utf8") as file:
            await file.write(compose_yaml)

    async def remove(self) -> None:
        if await self._compose_manager.created():
            raise RuntimeError(f"Cannot remove server {self._name} while it is created")
        await async_rmtree(self._project_path)

    async def up(self) -> None:
        await self._compose_manager.up_detached()

    async def down(self) -> None:
        await self._compose_manager.down()

    async def start(self) -> None:
        await self._compose_manager.start()

    async def stop(self) -> None:
        await self._compose_manager.stop()

    async def restart(self) -> None:
        await self._compose_manager.restart()

    async def exists(self) -> bool:
        """
        exists means that the server has a compose file
        """
        compose_file_path = await self.get_compose_file_path()
        return compose_file_path is not None

    async def created(self) -> bool:
        """
        created means that the container has been created but it is not running
        """
        return await self._compose_manager.created()

    async def running(self) -> bool:
        return await self._compose_manager.running()

    async def starting(self) -> bool:
        return await self._compose_manager.starting("mc")

    async def healthy(self) -> bool:
        return await self._compose_manager.healthy("mc")

    async def get_status(self) -> MCServerStatus:
        """
        Get the current status of the Minecraft server

        Returns the highest status level that the server has achieved.
        Status levels are hierarchical - if a server is healthy, it's also
        running, created, and exists.

        Returns:
            MCServerStatus: The current server status
        """
        # Check in reverse hierarchical order (highest to lowest)
        if not await self.exists():
            return MCServerStatus.REMOVED

        if not await self.created():
            return MCServerStatus.EXISTS

        if not await self.running():
            return MCServerStatus.CREATED

        if await self.starting():
            return MCServerStatus.STARTING

        if not await self.healthy():
            return MCServerStatus.RUNNING

        return MCServerStatus.HEALTHY

    async def wait_until_healthy(self) -> None:
        if not await self.running():
            raise RuntimeError(f"Server {self._name} is not running")
        while not await self.healthy():
            await asyncio.sleep(0.5)

    async def get_disk_space_info(self) -> DiskSpaceInfo:
        """
        获取服务器数据目录的完整磁盘空间信息

        Returns:
            DiskSpaceInfo: Contains used, total, and available disk space in bytes

        Raises:
            RuntimeError: If data directory does not exist
        """
        if not await aioos.path.exists(self._project_path / "data"):
            raise RuntimeError(f"Data directory does not exist for server {self._name}")

        # Get used space with du command
        du_result = await exec_command("du", "-sb", str(self._project_path / "data"))
        du_usage_str = du_result.split()[0]
        try:
            used_bytes = int(du_usage_str)
        except ValueError:
            used_bytes = 0

        # Get filesystem information with df command
        df_result = await exec_command("df", "-B1", str(self._project_path / "data"))
        # df output format: Filesystem 1B-blocks Used Available Use% Mounted on
        # We want the second line with the actual data
        df_lines = df_result.strip().split("\n")
        if len(df_lines) < 2:
            raise RuntimeError(
                f"Unable to get filesystem info for {self._project_path / 'data'}"
            )

        # Parse df output - handle case where filesystem name might be on separate line
        df_data_line = df_lines[1]
        if len(df_lines) > 2 and not df_data_line.strip().split()[0].isdigit():
            # Filesystem name is on separate line, data is on next line
            df_data_line = df_lines[2] if len(df_lines) > 2 else df_lines[1]

        df_parts = df_data_line.strip().split()
        if len(df_parts) < 4:
            raise RuntimeError(f"Unable to parse df output: {df_result}")

        try:
            total_bytes = int(df_parts[1])  # 1B-blocks (total)
            available_bytes = int(df_parts[3])  # Available
        except (ValueError, IndexError):
            raise RuntimeError(f"Unable to parse df output numbers: {df_result}")

        return DiskSpaceInfo(
            used_bytes=used_bytes,
            total_bytes=total_bytes,
            available_bytes=available_bytes,
        )

    async def get_server_info(self):
        """
        获取服务器信息

        使用MCComposeFile进行强类型访问，一旦MCComposeFile创建成功，
        就意味着所有必需的字段都已经验证并且类型正确。
        """
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

    async def list_players(self) -> list[str]:
        players = await self.send_command_rcon("list")
        if ":" not in players:
            return []
        players_str = players.split(":")[1].strip()
        return [
            player.strip() for player in players_str.split(",") if player.strip() != ""
        ]

    async def send_command_rcon(self, command: str) -> str:
        """
        this method will send a command to the server using rcon
            we are actually just using rcon-cli provided by itzg/minecraft-server
            to get rid of extra dependencies
        """
        if not await self.healthy():
            raise RuntimeError(f"Server {self._name} is not healthy")
        result = await self._compose_manager.exec("mc", "rcon-cli", command)
        return ANSI_ESCAPE_PATTERN.sub("", result).strip()

    async def send_command_stdin(self, command: str):
        """
        this method will send a command to the server using mc-send-to-console
        """
        if not await self.running():
            raise RuntimeError(f"Server {self._name} is not running")
        uid, _ = await get_uid_gid(self.get_project_path())
        await self._compose_manager.exec(
            "--user", str(uid), "mc", "mc-send-to-console", command
        )

    async def get_container_id(self) -> str:
        """Get the Docker container ID for the mc service."""
        if not await self.created():
            raise RuntimeError(f"Server {self._name} is not created")

        container_id = await self._compose_manager.run_compose_command(
            "ps", "--all", "-q", "mc"
        )
        container_id = container_id.strip()

        if not container_id:
            raise RuntimeError(
                f"Could not find container ID for service 'mc' in server {self._name}"
            )

        return container_id

    async def get_pid(self) -> int:
        """Get the Java process PID from the Docker container using docker compose top"""
        result = await self._compose_manager.run_compose_command("top")

        lines = result.strip().split("\n")

        if not lines:
            raise RuntimeError(
                f"docker compose top command returned no processes for server {self._name}"
            )

        first_line = lines[0]
        if first_line.strip().startswith("SERVICE"):
            column_num = 10
            pid_column = 3
        else:
            column_num = 8
            pid_column = 1

        for line in lines[1:]:
            parts = line.split(maxsplit=column_num - 1)
            if len(parts) >= column_num:
                cmd = parts[pid_column]
                if cmd.strip().startswith("java"):
                    pid_str = parts[1]
                    try:
                        return int(pid_str)
                    except ValueError:
                        continue

        raise RuntimeError(f"Could not find Java process PID for server {self._name}")

    async def get_memory_usage(self) -> MemoryStats:
        """Get memory usage statistics from cgroup for the container."""
        container_id = await self.get_container_id()
        return await read_memory_stats(container_id)

    async def get_cpu_percentage(self) -> float:
        """Get CPU usage percentage for the container process."""
        pid = await self.get_pid()
        return await get_process_cpu_usage(pid)

    async def get_disk_io(self) -> BlockIOStats:
        """Get disk I/O statistics from cgroup for the container."""
        container_id = await self.get_container_id()
        return await read_block_io_stats(container_id)

    async def get_network_io(self) -> NetworkStats:
        """Get network I/O statistics for the container process."""
        pid = await self.get_pid()
        return await read_container_network_stats(pid)
