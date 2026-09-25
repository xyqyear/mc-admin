from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.background_tasks import BackgroundTaskManager, TaskType
from app.configuration.application import rebuild_server_task
from app.configuration.state import read_configuration_state
from app.db.metadata import Base
from app.minecraft import MCServerStatus, get_docker_mc_manager
from app.operations.journal import OperationJournal
from app.operations.recovery import RecoveryService
from app.runtime import Runtime
from app.servers.models import Server

COMPOSE = '''services:
  mc:
    container_name: mc-first
    image: itzg/minecraft-server:latest
    environment:
      VERSION: "1.21.8"
      MEMORY: "2G"
    ports:
      - "25565:25565"
      - "25575:25575"
'''


@dataclass
class ConfigurationHarness:
    runtime: Runtime
    journal: OperationJournal
    tasks: BackgroundTaskManager
    recovery: RecoveryService
    compose: Path
    down: AsyncMock
    up: AsyncMock
    status: AsyncMock
    created: AsyncMock

    async def state(self):
        async with self.journal.session_factory() as db:
            return await read_configuration_state(db, "first", self.compose.parent.parent)

    async def submit(self, configuration):
        return await self.tasks.submit_durable(
            TaskType.SERVER_REBUILD, "配置测试", rebuild_server_task("first", configuration),
            server_id="first", configuration_version=configuration.fingerprint,
        )


@pytest.fixture
async def configuration(isolated_runtime, monkeypatch):
    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with isolated_runtime.database.session_factory() as session:
        session.add(Server(id=1, server_id="first"))
        await session.commit()
    instance = get_docker_mc_manager().get_instance("first")
    await instance.create(COMPOSE)
    status = AsyncMock(return_value=MCServerStatus.EXISTS)
    down, up = AsyncMock(), AsyncMock()
    created = AsyncMock(return_value=False)
    monkeypatch.setattr(instance, "get_status", status)
    monkeypatch.setattr(instance, "down", down)
    monkeypatch.setattr(instance, "up", up)
    monkeypatch.setattr(instance, "created", created)
    monkeypatch.setattr(get_docker_mc_manager(), "get_instance", lambda _: instance)
    monkeypatch.setattr("app.configuration.application.check_port_conflicts", AsyncMock(return_value=[]))
    journal = OperationJournal(isolated_runtime.database.session_factory)
    tasks = BackgroundTaskManager(journal)
    isolated_runtime.journal = journal
    isolated_runtime.resources["task_manager"] = tasks
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=True), servers_root=isolated_runtime.settings.server_path)
    isolated_runtime.resources["operation_recovery"] = recovery
    yield ConfigurationHarness(isolated_runtime, journal, tasks, recovery, instance.get_project_path() / "docker-compose.yml", down, up, status, created)
    await tasks.shutdown()
