from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.cron import crud
from app.cron.jobs import backup
from app.cron.manager import CronManager
from app.cron.models import ExecutionStatus
from app.db.metadata import Base
from app.dynamic_config.configs.snapshots import SnapshotsConfig
from app.minecraft import get_docker_mc_manager
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState, ResourceReference
from app.servers.models import Server
from app.snapshots import ResticClient, SnapshotService
from app.utils.exec import exec_command
from app.world.locks import LockHolder, ServerOperationKind, get_server_operation_lock
from tests.support.runtime import replace_runtime_resource


@pytest.mark.binary("restic")
@pytest.mark.parametrize("busy", [False, True])
async def test_global_backup_records_success_or_skip_with_nested_file_scope(isolated_runtime, tmp_path, busy):
    runtime = isolated_runtime
    replace_runtime_resource(runtime, "dynamic_configuration", SimpleNamespace(snapshots=SnapshotsConfig()))
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with runtime.database.session_factory() as session:
        session.add(Server(server_id="survival"))
        await session.commit()
        await crud.create_cronjob(
            session, cronjob_id="global-backup", identifier="backup", name="全局备份",
            cron="0 0 * * *", params_json='{"enable_forget": false}',
        )
    project = runtime.settings.server_path / "survival"
    (project / "data").mkdir(parents=True)
    (project / "compose.yaml").write_text(
        "services:\n"
        "  mc:\n"
        "    container_name: mc-survival\n"
        "    image: itzg/minecraft-server:java21\n"
        "    environment: {VERSION: '1.21.1'}\n"
        "    ports: ['25565:25565', '25575:25575']\n"
    )
    assert [instance.get_name() for instance in await get_docker_mc_manager().get_all_instances()] == ["survival"]
    client = ResticClient(str(tmp_path / "repository"), password="cron-backup-test")
    await exec_command(str(client.binary_path), "init", env=client.env)
    snapshots = SnapshotService(client, get_docker_mc_manager())
    replace_runtime_resource(runtime, "snapshot_service", snapshots)
    (project / "data" / "settings.txt").write_text("retained cron data")
    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    manager = CronManager()

    @asynccontextmanager
    async def maintenance():
        if busy:
            holder = LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), None, "世界恢复")
            async with get_server_operation_lock().acquire("survival", holder):
                yield
        else:
            yield

    async with maintenance():
        await manager._execute_cronjob_wrapper(
            "global-backup", "backup", backup.BackupJobParams(enable_forget=False), backup.backup_cronjob,
        )
    rows = await manager.get_execution_history("global-backup")
    assert len(rows) == 1
    assert rows[0].status == (ExecutionStatus.SKIPPED if busy else ExecutionStatus.COMPLETED)
    records = await journal.list()
    assert len(records) == 1
    record = records[0]
    assert record.kind == "cron_backup"
    assert record.state == (OperationState.SKIPPED if busy else OperationState.SUCCEEDED)
    assert ResourceReference("files") in record.resources
    assert record.writers_stopped and not record.processes
    if busy:
        assert await snapshots.list_snapshots() == []
        assert any("跳过备份" in message for message in rows[0].messages)
    else:
        saved = await snapshots.list_snapshots()
        assert len(saved) == 1 and saved[0].paths == [str(runtime.settings.server_path)]
        assert (project / "data" / "settings.txt").read_text() == "retained cron data"
