from types import SimpleNamespace

import pytest

from app.background_tasks.manager import BackgroundTaskManager
from app.minecraft import MCServerStatus
from app.operations.journal import OperationJournal
from app.runtime_resources import current_runtime
from app.servers.models import Server
from app.snapshots.commands import SnapshotCommands
from app.snapshots.notes import SnapshotNotes
from app.snapshots.restic import ResticClient
from app.snapshots.service import SnapshotService
from app.utils.exec import exec_command
from tests.support.regions import region_bytes
from tests.support.runtime import replace_runtime_resource


@pytest.fixture
async def case(tmp_path, database, runtime_config):
    runtime = current_runtime()
    root = runtime.settings.server_path
    project = root / "survival"
    data = project / "data"
    data.mkdir(parents=True)
    (project / "compose.yaml").write_text("services: {}\n")
    (data / "server.properties").write_text("level-name=world\n")

    class Instance:
        status = MCServerStatus.EXISTS

        def get_name(self):
            return "survival"

        def get_project_path(self):
            return project

        def get_data_path(self):
            return data

        async def get_status(self):
            return self.status

    instance = Instance()

    class Manager:
        servers_path = root

        async def get_all_instances(self):
            return [instance]

        def get_instance(self, _):
            return instance

    config = runtime_config
    config.snapshots.ignored_paths = []
    replace_runtime_resource(runtime, "docker_mc_manager", Manager())
    async with runtime.database.session_factory() as session:
        session.add(Server(server_id="survival"))
        await session.commit()
    runtime.journal = OperationJournal(runtime.database.session_factory)
    tasks = BackgroundTaskManager(runtime.journal)
    replace_runtime_resource(runtime, "task_manager", tasks)
    client = ResticClient(
        repository_path=str(tmp_path / "repository"), password="command-test"
    )
    try:
        await exec_command(str(client.binary_path), "init", env=client.env)
        snapshots = SnapshotService(client, Manager(), SnapshotNotes(runtime.database.session_factory))
        replace_runtime_resource(runtime, "snapshot_service", snapshots)
        commands = runtime.snapshot_commands
        assert isinstance(commands, SnapshotCommands)
        yield SimpleNamespace(
            commands=commands,
            snapshots=snapshots,
            data=data,
            tasks=tasks,
            config=config,
            journal=runtime.journal,
            instance=instance,
            client=client,
        )
    finally:
        await tasks.shutdown()
        if runtime.snapshot_previews is not None:
            await runtime.snapshot_previews.close()


@pytest.fixture
def world_case(case):
    triggers = case.config.self_check.event_triggers
    triggers.after_server_created = False
    triggers.after_server_populated = False
    triggers.after_world_restored = False
    triggers.after_world_rolled_back = False
    world = case.data / "world"
    region = world / "region"
    region.mkdir(parents=True)
    (world / "level.dat").write_bytes(b"world metadata")
    (region / "r.0.0.mca").write_bytes(region_bytes(["source zero", "source one"]))
    case.region = region
    return case
