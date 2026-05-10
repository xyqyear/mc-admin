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
    container_name: str
    image: str
    ports: List[Ports]
    volumes: List[Volumes]
    environment: Dict[str, str | float | bool]
    stdin_open: bool
    tty: bool
    restart: str


class MCServices(BaseModel):
    mc: MCService


class MCComposeFile(BaseModel):
    """Validated Minecraft compose file; all checks happen at construction."""

    version: str | None = None
    name: str | None = None
    services: MCServices
    volumes: Dict[str, Any] | None = None

    def __init__(self, compose_obj: ComposeFile):
        """Raises ``ValueError`` if ``compose_obj`` doesn't meet Minecraft server requirements."""
        validated_services = self._validate_and_convert_services(compose_obj)

        super().__init__(
            version=compose_obj.version,
            name=compose_obj.name,
            services=validated_services,
            volumes=compose_obj.volumes,
        )

    @staticmethod
    def _validate_and_convert_services(compose_obj: ComposeFile) -> MCServices:
        if compose_obj.services is None:
            raise ValueError("Could not find services in compose file")

        if "mc" not in compose_obj.services:
            raise ValueError("Could not find service mc in compose file")

        mc_service = compose_obj.services["mc"]

        if not isinstance(mc_service.container_name, str):
            raise ValueError("Invalid container name in compose file")
        if not mc_service.container_name.startswith("mc-"):
            raise ValueError("Container name must start with 'mc-'")

        if mc_service.image is None or "itzg/minecraft-server" not in mc_service.image:
            raise ValueError("Service must use itzg/minecraft-server image")

        if not isinstance(mc_service.environment, dict):
            raise ValueError("Invalid environment in compose file")
        environment = cast(Dict[str, str | float | bool], mc_service.environment)

        if "VERSION" not in environment:
            raise ValueError("Could not find VERSION in environment")

        if mc_service.ports is None:
            raise ValueError("Could not find ports in compose file")
        ports = cast(List[Ports], mc_service.ports)

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
        return self.services.mc

    def get_server_name(self) -> str:
        return self.mc_service.container_name[3:]

    def get_game_port(self) -> int:
        for port in self.mc_service.ports:
            if str(port.target) == "25565":
                if port.published is None:
                    return 25565
                return int(port.published)
        raise ValueError("Could not find game port in compose file")

    def get_rcon_port(self) -> int:
        for port in self.mc_service.ports:
            if str(port.target) == "25575":
                if port.published is None:
                    return 25575
                return int(port.published)
        raise ValueError("Could not find rcon port in compose file")

    def get_game_version(self) -> str:
        version = self.mc_service.environment["VERSION"]
        return str(version)

    def get_server_type(self) -> ServerType:
        if "TYPE" not in self.mc_service.environment:
            return ServerType.VANILLA
        server_type_value = self.mc_service.environment["TYPE"]
        return ServerType(str(server_type_value))

    def get_java_version(self) -> int:
        # Match the version digits in tags like itzg/minecraft-server:java21-graalvm.
        image = self.mc_service.image
        match = re.search(r"itzg/minecraft-server:java(\d+)", image)
        if match:
            return int(match.group(1))
        return 0

    def get_max_memory_bytes(self) -> int:
        if "MAX_MEMORY" in self.mc_service.environment:
            memory_value = self.mc_service.environment["MAX_MEMORY"]
            memory_str = str(memory_value)
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
                    # No suffix: itzg defaults to MB.
                    return value * 1024 * 1024
            return 0
        return 0
