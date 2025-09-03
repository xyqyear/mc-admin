import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..utils import exec_command, run_shell_command


class DockerPsParsed(BaseModel):
    command: str = Field(alias="Command")
    created_at: str = Field(alias="CreatedAt")
    id: str = Field(alias="ID")
    image: str = Field(alias="Image")
    labels: dict[str, str] = Field(alias="Labels")
    local_volumes: str = Field(alias="LocalVolumes")
    mounts: str = Field(alias="Mounts")
    names: str = Field(alias="Names")
    networks: str = Field(alias="Networks")
    ports: str = Field(alias="Ports")
    running_for: str = Field(alias="RunningFor")
    size: str = Field(alias="Size")
    state: str = Field(alias="State")
    status: str = Field(alias="Status")

    @classmethod
    def parse_labels(cls, labels_str: str) -> dict[str, str]:
        return dict(label.split("=") for label in labels_str.split(",") if "=" in label)

    @classmethod
    def from_docker_ps(cls, data: dict[str, Any]) -> "DockerPsParsed":
        data["Labels"] = cls.parse_labels(data["Labels"])
        return cls(**data)


class Publisher(BaseModel):
    URL: str
    TargetPort: int
    PublishedPort: int
    Protocol: str


class DockerComposePsParsed(DockerPsParsed):
    exit_code: int = Field(alias="ExitCode")
    health: str = Field(alias="Health")
    name: str = Field(alias="Name")
    project: str = Field(alias="Project")
    publishers: list[Publisher] = Field(alias="Publishers")
    service: str = Field(alias="Service")

    @classmethod
    def from_docker_compose_ps(cls, data: dict[str, Any]) -> "DockerComposePsParsed":
        data["Labels"] = cls.parse_labels(data["Labels"])
        return cls(**data)


def sanitize_command(command: str) -> str:
    return command


class ComposeManager:
    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)

    async def run_compose_command(self, *args: str) -> str:
        return await exec_command(
            "docker",
            "compose",
            "--project-directory",
            str(self.project_path),
            *args,
        )

    async def exec(self, service_name: str, *args: str) -> str:
        return await self.run_compose_command("exec", service_name, *args)

    async def send_to_stdin(self, service_name: str, text: str):
        """
        Deprecated, used in tests only.
        """
        # apparently, create_subprocess_shell is going to eat another escape
        # and we don't need to escape < and >
        text = text.replace("\\", "\\\\\\\\").replace('"', '\\"').replace("$", "\\$")
        await run_shell_command(
            f'echo "{text}" | socat "EXEC:docker compose --project-directory {self.project_path} attach {service_name},pty" STDIN',
            catch_output=False,
        )

    async def up_detached(self):
        await self.run_compose_command("up", "-d")

    async def down(self):
        await self.run_compose_command("down")

    async def stop(self):
        await self.run_compose_command("stop")

    async def start(self):
        await self.run_compose_command("start")

    async def restart(self):
        await self.run_compose_command("restart")

    async def pull(self):
        await self.run_compose_command("pull")

    async def logs(self, tail: int = 1000) -> str:
        return await self.run_compose_command("logs", "--tail", str(tail))

    async def running(self) -> bool:
        try:
            process = await self.run_compose_command("ps", "-q")
        except RuntimeError as e:
            if "no configuration file" in str(e):
                return False
            raise e
        return process != ""

    async def created(self) -> bool:
        try:
            process = await self.run_compose_command("ps", "--all", "-q")
        except RuntimeError as e:
            if "no configuration file" in str(e):
                return False
            raise e
        return process != ""

    async def ps(self, service_name: str) -> DockerComposePsParsed:
        output = await self.run_compose_command("ps", "--no-trunc", "--format", "json")
        for line in output.splitlines():
            parsed = DockerComposePsParsed.from_docker_compose_ps(json.loads(line))
            if parsed.service == service_name:
                return parsed
        raise ValueError(f"Could not find service {service_name}")

    async def starting(self, service_name: str) -> bool:
        try:
            compose_ps = await self.ps(service_name)
        except ValueError:
            return False
        except RuntimeError as e:
            if "no configuration file" in str(e):
                return False
            raise e
        return compose_ps.health == "starting"

    async def healthy(self, service_name: str) -> bool:
        try:
            compose_ps = await self.ps(service_name)
        except ValueError:
            return False
        except RuntimeError as e:
            if "no configuration file" in str(e):
                return False
            raise e
        return compose_ps.health == "healthy"


class DockerManager:
    @staticmethod
    async def run_sub_command(*args: str) -> str:
        return await exec_command("docker", *args)

    @classmethod
    async def ps(cls):
        output = await cls.run_sub_command("ps", "--no-trunc", "--format", "json")
        return [
            DockerPsParsed.from_docker_ps(json.loads(line))
            for line in output.splitlines()
        ]
