import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from app.utils.exec import exec_command

OWNER_LABEL = "io.mc-admin.pytest.owner"
MINECRAFT_IMAGE = "itzg/minecraft-server:java25@sha256:59feb0a1ef286f20a20560c56adf5b927155bfa842951f5db8b8bbc5a1a3ebde"


def create_mc_server_compose_yaml(server_name: str, game_port: int, rcon_port: int, *, owner: str | None = None) -> str:
    labels = {OWNER_LABEL: owner} if owner else {}
    return yaml.safe_dump({
        "services": {"mc": {
            "image": MINECRAFT_IMAGE,
            "container_name": f"mc-{server_name}",
            "labels": labels,
            "environment": {
                "EULA": "true", "VERSION": "1.21.11", "INIT_MEMORY": "0M", "MAX_MEMORY": "500M",
                "ONLINE_MODE": "false", "TYPE": "VANILLA", "ENABLE_RCON": "true", "MODE": "creative",
                "VIEW_DISTANCE": "1", "LEVEL_TYPE": "minecraft:flat", "GENERATE_STRUCTURES": "false",
                "SPAWN_NPCS": "false", "SPAWN_ANIMALS": "false", "SPAWN_MONSTERS": "false",
                "FORCE_GAMEMODE": "true", "UID": str(os.getuid()), "GID": str(os.getgid()),
            },
            "ports": [f"{game_port}:25565", f"{rcon_port}:25575"],
            "volumes": ["./data:/data"], "stdin_open": True, "tty": True, "restart": "unless-stopped",
        }},
        "networks": {"default": {"labels": labels}},
    }, sort_keys=False)


@dataclass
class OwnedDockerResources:
    root: Path
    owner: str = field(default_factory=lambda: uuid.uuid4().hex)
    containers: list[str] = field(default_factory=list)

    def name(self, suffix: str) -> str:
        return f"pytest-{self.owner[:12]}-{suffix}"

    def compose(self, server_name: str, game_port: int, rcon_port: int) -> str:
        self.containers.append(f"mc-{server_name}")
        return create_mc_server_compose_yaml(server_name, game_port, rcon_port, owner=self.owner)

    async def remove(self, kind: str, name: str) -> None:
        try:
            output = await exec_command("docker", kind, "inspect", name)
        except RuntimeError as error:
            if "No such" in str(error):
                return
            raise
        resource = json.loads(output)[0]
        labels = (resource.get("Config", {}).get("Labels") if kind == "container" else resource.get("Labels")) or {}
        if labels.get(OWNER_LABEL) != self.owner:
            raise RuntimeError(f"Refusing to remove {kind} without this test's ownership: {name}")
        identifier = resource["Id"]
        command = ("rm", "-f", identifier) if kind == "container" else ("network", "rm", identifier)
        await exec_command("docker", *command)

    async def cleanup(self) -> None:
        errors = []
        for name in reversed(self.containers):
            try:
                await self.remove("container", name)
            except (RuntimeError, OSError, ValueError, LookupError, TypeError) as error:
                errors.append(error)
        networks = await exec_command("docker", "network", "ls", "--filter", f"label={OWNER_LABEL}={self.owner}", "--format", "{{.ID}}")
        for identifier in networks.splitlines():
            try:
                await self.remove("network", identifier)
            except (RuntimeError, OSError, ValueError, LookupError, TypeError) as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Owned Docker cleanup failed", errors)


@pytest.fixture
async def owned_docker_resources(tmp_path: Path, request: pytest.FixtureRequest):
    if not request.node.get_closest_marker("docker") or not request.config.getoption("--run-docker"):
        pytest.fail("Owned Docker fixture requires @pytest.mark.docker and --run-docker")
    resources = OwnedDockerResources(tmp_path)
    try:
        yield resources
    finally:
        await resources.cleanup()
