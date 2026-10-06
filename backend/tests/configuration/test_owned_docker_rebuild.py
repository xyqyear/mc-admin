import asyncio

import pytest

from app.background_tasks import TaskType
from app.configuration.application import rebuild_server_task
from app.configuration.preparation import ServerConfiguration
from app.configuration.state import read_configuration_state
from app.db.metadata import Base
from app.minecraft import DockerMCManager
from app.minecraft.docker.manager import DockerManager
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.runtime import Runtime
from app.servers.models import Server
from tests.fixtures.test_utils import (
    OwnedDockerResources,
    owned_docker_resources,  # noqa: F401
)
from tests.support.runtime import replace_runtime_resource


@pytest.mark.docker
async def test_configuration_task_rebuilds_real_container_environment(
    isolated_runtime: Runtime, owned_docker_resources: OwnedDockerResources,  # noqa: F811
):
    resources = owned_docker_resources
    isolated_runtime.settings.server_path = resources.root
    manager = DockerMCManager(resources.root)
    replace_runtime_resource(isolated_runtime, "docker_mc_manager", manager)
    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    journal = OperationJournal(isolated_runtime.database.session_factory)
    isolated_runtime.journal = journal
    server_name = resources.name("configuration")
    async with isolated_runtime.database.session_factory() as db:
        db.add(Server(server_id=server_name))
        await db.commit()
    server = manager.get_instance(server_name)
    original = resources.compose(server_name)
    await server.create(original)
    await server.up()
    await server.wait_until_healthy()
    original_container = await server.get_container_id()
    async with isolated_runtime.database.session_factory() as db:
        baseline = await read_configuration_state(db, server_name, resources.root)
    assert "MODE: creative" in original
    configuration = ServerConfiguration(
        original.replace("MODE: creative", "MODE: survival"),
        expected_version=baseline.version,
    )
    submitted = await isolated_runtime.task_manager.submit_durable(
        TaskType.SERVER_REBUILD, "重建测试服务器", rebuild_server_task(server_name, configuration),
        server_id=server_name, configuration_version=configuration.fingerprint,
    )
    result = await asyncio.wait_for(submitted.awaitable, 120)
    assert result.success, result.error
    assert result.data is not None and result.data["was_running"] is True
    record = await journal.get(submitted.task_id)
    assert record is not None and record.state == OperationState.SUCCEEDED
    assert record.running_intent is True
    await server.wait_until_healthy()
    assert await server.get_container_id() != original_container
    environment = await DockerManager.run_sub_command(
        "inspect", f"mc-{server_name}", "--format", "{{range .Config.Env}}{{println .}}{{end}}",
    )
    assert "MODE=survival" in environment.splitlines()
    assert "MODE=creative" not in environment.splitlines()
    assert await server.get_compose_file() == configuration.yaml_content
    async with isolated_runtime.database.session_factory() as db:
        current = await read_configuration_state(db, server_name, resources.root)
    assert current.version == result.data["version"]
    assert current.version != baseline.version
    assert current.template_id is None
    assert current.snapshot_json is None
    assert current.values_json is None
    assert current.source_version == baseline.source_version
    assert not list(server.get_project_path().glob(".mc-admin-configuration-*.tmp"))
