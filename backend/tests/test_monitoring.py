"""Shared samples against an owned, real Minecraft container."""

import asyncio

import psutil
import pytest

from app.minecraft.docker.reader import DockerReader
from app.minecraft.manager import DockerMCManager
from app.minecraft.status import MCServerStatus
from app.monitoring.models import Sample, ServerSamples
from app.monitoring.service import RuntimeMonitor
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.servers.commands import ServerCommands
from app.servers.crud import create_server_record
from app.snapshots.file_restore import FileRestoreAdapter, SnapshotServerRunning
from app.world.locks import ServerOperationLock
from tests.fixtures.test_utils import OwnedDockerResources

pytestmark = pytest.mark.docker


async def test_running_container_metrics_observe_real_activity(tmp_path, database, isolated_runtime):
    resources = OwnedDockerResources(tmp_path)
    name = resources.name("monitoring")
    manager = DockerMCManager(resources.root)
    server = manager.get_instance(name)
    reader = DockerReader()
    monitor = RuntimeMonitor(database.session_factory, manager, reader)
    try:
        await server.create(resources.compose(name))
        async with database.session_factory() as session:
            record = await create_server_record(session, name)
        await server.up()
        await asyncio.wait_for(server.wait_until_healthy(), 120)
        state = await reader.observe(await server.get_project_target())
        assert state.container is not None
        java = psutil.Process(await reader.java_pid(state.container.container_id))
        assert java.name() == "java"
        isolated_runtime.monitor.servers[record.id] = ServerSamples(
            generation=record.id, status=Sample.ready(MCServerStatus.CREATED),
        )
        with pytest.raises(SnapshotServerRunning):
            await FileRestoreAdapter(manager, ServerOperationLock()).check_available([name])
        await monitor.sample_servers()
        assert monitor.servers[record.id].cpu_percent.quality == "pending"
        await asyncio.sleep(0.2)
        await monitor.sample_servers()
        current = monitor.servers[record.id]
        assert current.cpu_percent.value is not None and current.cpu_percent.value >= 0
        assert current.memory_bytes.value is not None and 10 * 1024 ** 2 < current.memory_bytes.value < 2 * 1024 ** 3
        assert current.disk_io.value is not None
        assert current.network_io.value is not None
        before = current.network_io.value
        await server.send_command_rcon("list")
        await monitor.sample_servers()
        after = monitor.servers[record.id].network_io.value
        assert after is not None and after.read > before.read and after.write > before.write
        await server.stop()
        await monitor.sample_servers()
        assert monitor.servers[record.id].cpu_percent.value is None
        assert monitor.servers[record.id].cpu_percent.quality == "unavailable"
    finally:
        await monitor.close()
        await reader.close()
        await resources.cleanup()


async def test_missing_container_is_not_claimed(tmp_path):
    server = DockerMCManager(tmp_path).get_instance("missing")
    with pytest.raises(RuntimeError, match="尚未创建"):
        await server.get_container_id()


async def test_start_uses_live_container_existence_and_preserves_existing_container(tmp_path, database, isolated_runtime, monkeypatch):
    from tests.support.runtime import set_runtime_resource

    resources = OwnedDockerResources(tmp_path)
    name = resources.name("start-intent")
    isolated_runtime.settings.server_path = resources.root
    manager = DockerMCManager(resources.root)
    set_runtime_resource(monkeypatch, "docker_mc_manager", manager)
    isolated_runtime.journal = OperationJournal(database.session_factory)
    server = manager.get_instance(name)
    commands = ServerCommands()
    original = resources.compose(name)
    try:
        await server.create(original)
        async with database.session_factory() as session:
            record = await create_server_record(session, name)
        isolated_runtime.monitor.servers[record.id] = ServerSamples(
            generation=record.id, status=Sample.ready(MCServerStatus.CREATED),
        )
        await commands.execute(name, "start")
        await asyncio.wait_for(server.wait_until_healthy(), 120)
        container_id = await server.get_container_id()
        await commands.execute(name, "stop")
        compose_path = await server.get_compose_file_path()
        assert compose_path is not None
        compose_path.write_text(original.replace("MODE: creative", "MODE: survival"))
        isolated_runtime.monitor.servers[record.id].status = Sample.ready(MCServerStatus.EXISTS)
        await commands.execute(name, "start")
        await asyncio.wait_for(server.wait_until_healthy(), 120)
        assert await server.get_container_id() == container_id
        assert (await server.get_server_properties()).gamemode == "creative"
        assert await server.send_command_rcon("list")
        history = await isolated_runtime.journal.list()
        assert len(history) == 3
        assert all(entry.state is OperationState.SUCCEEDED and entry.writers_stopped for entry in history)
        assert isolated_runtime.server_write_admission.recovery_reason(name) is None
    finally:
        await resources.cleanup()
