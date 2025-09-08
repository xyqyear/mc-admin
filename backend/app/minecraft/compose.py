import re
from enum import Enum
from typing import Any, Dict, List, cast

from pydantic import BaseModel

from .docker.compose_file import ComposeFile, Ports, Volumes


class ServerType(str, Enum):
    VANILLA = "VANILLA"
    PAPER = "PAPER"
    FORGE = "FORGE"
    NEOFORGE = "NEOFORGE"
    FABRIC = "FABRIC"
    SPIGOT = "SPIGOT"
    BUKKIT = "BUKKIT"
    CUSTOM = "CUSTOM"


class MCService(BaseModel):
    """强类型的Minecraft服务定义"""

    container_name: str
    image: str
    ports: List[Ports]
    volumes: List[Volumes]
    environment: Dict[str, str | float | bool]
    stdin_open: bool
    tty: bool
    restart: str


class MCServices(BaseModel):
    """强类型的Services，确保包含mc服务"""

    mc: MCService


class MCComposeFile(BaseModel):
    """强类型的Minecraft Compose文件模型

    这个模型在初始化时完成所有验证和类型转换，
    之后使用时就是完全强类型的，无需重复检查。
    """

    version: str | None = None
    name: str | None = None
    services: MCServices
    volumes: Dict[str, Any] | None = None

    def __init__(self, compose_obj: ComposeFile):
        """从ComposeFile对象创建MCComposeFile

        Args:
            compose_obj: 原始的ComposeFile对象

        Raises:
            ValueError: 如果compose文件不符合Minecraft服务器要求
        """
        # 在初始化时完成所有验证和转换
        validated_services = self._validate_and_convert_services(compose_obj)

        super().__init__(
            version=compose_obj.version,
            name=compose_obj.name,
            services=validated_services,
            volumes=compose_obj.volumes,
        )

    @staticmethod
    def _validate_and_convert_services(compose_obj: ComposeFile) -> MCServices:
        """验证并转换services为强类型结构

        Args:
            compose_obj: 原始的ComposeFile对象

        Returns:
            强类型的MCServices对象

        Raises:
            ValueError: 如果验证失败
        """
        if compose_obj.services is None:
            raise ValueError("Could not find services in compose file")

        if "mc" not in compose_obj.services:
            raise ValueError("Could not find service mc in compose file")

        mc_service = compose_obj.services["mc"]

        # 验证容器名
        if not isinstance(mc_service.container_name, str):
            raise ValueError("Invalid container name in compose file")
        if not mc_service.container_name.startswith("mc-"):
            raise ValueError("Container name must start with 'mc-'")

        # 验证镜像
        if mc_service.image is None or "itzg/minecraft-server" not in mc_service.image:
            raise ValueError("Service must use itzg/minecraft-server image")

        # 验证和转换环境变量（ComposeFile已经转换为dict）
        if not isinstance(mc_service.environment, dict):
            raise ValueError("Invalid environment in compose file")
        environment = cast(Dict[str, str | float | bool], mc_service.environment)

        # 验证必需的环境变量
        if "VERSION" not in environment:
            raise ValueError("Could not find VERSION in environment")

        # 验证端口（ComposeFile已经转换为Ports对象）
        if mc_service.ports is None:
            raise ValueError("Could not find ports in compose file")
        ports = cast(List[Ports], mc_service.ports)

        # 验证必需的端口
        has_game_port = False
        has_rcon_port = False
        for port in ports:
            if str(port.target) == "25565":
                has_game_port = True
            elif str(port.target) == "25575":
                has_rcon_port = True

        if not has_game_port:
            raise ValueError("Could not find game port (25565) in compose file")
        if not has_rcon_port:
            raise ValueError("Could not find rcon port (25575) in compose file")

        # 验证和转换卷（ComposeFile已经转换为Volumes对象）
        if mc_service.volumes is None:
            volumes = []
        else:
            volumes = cast(List[Volumes], mc_service.volumes)

        return MCServices(
            mc=MCService(
                container_name=mc_service.container_name,
                image=mc_service.image,
                ports=ports,
                volumes=volumes,
                environment=environment,
                stdin_open=bool(mc_service.stdin_open),
                tty=bool(mc_service.tty),
                restart=mc_service.restart or "unless-stopped",
            )
        )

    @property
    def mc_service(self) -> MCService:
        """直接访问mc服务，无需类型检查"""
        return self.services.mc

    def get_server_name(self) -> str:
        """获取服务器名称"""
        return self.mc_service.container_name[3:]  # 移除"mc-"前缀

    def get_game_port(self) -> int:
        """获取游戏端口"""
        for port in self.mc_service.ports:
            if str(port.target) == "25565":
                if port.published is None:
                    return 25565
                return int(port.published)
        raise ValueError("Could not find game port in compose file")

    def get_rcon_port(self) -> int:
        """获取RCON端口"""
        for port in self.mc_service.ports:
            if str(port.target) == "25575":
                if port.published is None:
                    return 25575
                return int(port.published)
        raise ValueError("Could not find rcon port in compose file")

    def get_game_version(self) -> str:
        """获取游戏版本"""
        version = self.mc_service.environment["VERSION"]
        return str(version)

    def get_server_type(self) -> ServerType:
        """获取服务器类型"""
        if "TYPE" not in self.mc_service.environment:
            return ServerType.VANILLA
        server_type_value = self.mc_service.environment["TYPE"]
        return ServerType(str(server_type_value))

    def get_java_version(self) -> int:
        """获取Java版本"""
        # itzg/minecraft-server:java8
        # itzg/minecraft-server:java21-graalvm
        # use regex to match
        image = self.mc_service.image
        match = re.search(r"itzg/minecraft-server:java(\d+)", image)
        if match:
            return int(match.group(1))
        return 0

    def get_max_memory_bytes(self) -> int:
        """获取最大内存，返回字节数"""
        if "MAX_MEMORY" in self.mc_service.environment:
            memory_value = self.mc_service.environment["MAX_MEMORY"]
            memory_str = str(memory_value)
            # Parse memory value with units (e.g., "500M", "1G", "512m", "2g")
            match = re.search(r"(\d+)([MmGgKk]?)", memory_str)
            if match:
                value = int(match.group(1))
                unit = match.group(2).upper() if match.group(2) else ""

                if unit == "K":
                    return value * 1024
                elif unit == "M":
                    return value * 1024 * 1024
                elif unit == "G":
                    return value * 1024 * 1024 * 1024
                else:
                    # No unit, assume MB (common for Minecraft)
                    return value * 1024 * 1024
            return 0
        return 0
