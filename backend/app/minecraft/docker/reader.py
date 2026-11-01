"""Owned, serialized reads of the Docker Engine."""

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker

from ...operations.finalization import finalize
from ..status import MCServerStatus

PROJECT = "com.docker.compose.project"
WORKING_DIR = "com.docker.compose.project.working_dir"
SERVICE = "com.docker.compose.service"
ONE_OFF = "com.docker.compose.oneoff"


@dataclass(frozen=True)
class ProjectTarget:
    path: Path
    container_name: str
    project_name: str | None


@dataclass(frozen=True)
class ContainerState:
    container_id: str
    started_at: str
    running: bool
    health: str

    @property
    def identity(self) -> str:
        return f"{self.container_id}:{self.started_at}"


@dataclass(frozen=True)
class ProjectState:
    status: MCServerStatus
    container: ContainerState | None = None


def project_containers(target: ProjectTarget, containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for container in containers:
        labels = container.get("Labels") or {}
        if not labels.get(PROJECT) or str(labels.get(ONE_OFF, "false")).lower() == "true":
            continue
        if os.path.normpath(labels.get(WORKING_DIR, "")) != os.path.normpath(str(target.path)):
            continue
        if target.project_name is not None and labels[PROJECT] != target.project_name:
            continue
        selected.append(container)
    projects = {container["Labels"][PROJECT] for container in selected}
    minecraft = [container for container in selected if container["Labels"].get(SERVICE) == "mc"]
    if len(projects) > 1 or len(minecraft) > 1:
        raise RuntimeError("无法确定服务器的 Docker 项目归属")
    if minecraft and f"/{target.container_name}" not in minecraft[0].get("Names", []):
        raise RuntimeError("Docker 容器与服务器配置不匹配")
    return selected


class DockerReader:
    def __init__(self, *, timeout: int = 2) -> None:
        self._timeout = timeout
        self._client: docker.DockerClient | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="docker-read")
        self._lock = asyncio.Lock()
        self._closing = False

    def _api(self):
        if self._client is None:
            self._client = docker.from_env(timeout=self._timeout)
        return self._client.api

    async def _call[T](self, read: Callable[[], T]) -> T:
        async with self._lock:
            if self._closing:
                raise RuntimeError("Docker 读取服务已关闭")
            # Cancellation cannot release the client while its thread is still using it.
            return await finalize(asyncio.get_running_loop().run_in_executor(self._executor, read))

    async def list_containers(self) -> list[dict[str, Any]]:
        return await self._call(lambda: self._api().containers(all=True, filters={"label": PROJECT}))

    async def observe(
        self, target: ProjectTarget, containers: list[dict[str, Any]] | None = None,
    ) -> ProjectState:
        listed = await self.list_containers() if containers is None else containers
        selected = project_containers(target, listed)
        if not selected:
            return ProjectState(MCServerStatus.EXISTS)
        running = False
        minecraft = None
        for container in selected:
            detail = await self._call(lambda identifier=container["Id"]: self._api().inspect_container(identifier))
            labels = detail.get("Config", {}).get("Labels") or {}
            if labels != container["Labels"] or detail["Id"] != container["Id"]:
                raise RuntimeError("Docker 容器归属在读取期间发生变化")
            state = detail["State"]
            running = running or state.get("Status") == "running"
            if labels.get(SERVICE) == "mc":
                minecraft = ContainerState(
                    detail["Id"], state.get("StartedAt", ""), state.get("Status") == "running",
                    (state.get("Health") or {}).get("Status", ""),
                )
        status = MCServerStatus.CREATED
        if running:
            status = MCServerStatus.RUNNING
            if minecraft is not None and minecraft.running:
                if minecraft.health == "starting":
                    status = MCServerStatus.STARTING
                elif minecraft.health == "healthy":
                    status = MCServerStatus.HEALTHY
        return ProjectState(status, minecraft)

    async def java_pid(self, container_id: str) -> int:
        processes = await self._call(lambda: self._api().top(container_id, ps_args="-eo pid,comm"))
        titles = processes["Titles"]
        pid_column = titles.index("PID")
        command_column = titles.index("COMMAND")
        pids = [int(row[pid_column]) for row in processes["Processes"]
                if row[command_column] == "java"]
        if len(pids) != 1:
            raise RuntimeError("无法确定服务器的 Java 进程")
        return pids[0]

    async def close(self) -> None:
        self._closing = True
        async with self._lock:
            if self._client is not None:
                await finalize(asyncio.get_running_loop().run_in_executor(self._executor, self._client.close))
                self._client = None
            self._executor.shutdown(wait=True)
