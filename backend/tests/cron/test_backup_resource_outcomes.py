from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cron import crud
from app.cron.jobs import backup
from app.cron.manager import CronManager
from app.cron.models import ExecutionStatus
from app.db.metadata import Base
from app.minecraft import get_docker_mc_manager
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState, ResourceReference
from app.servers.models import Server
from app.world.locks import LockHolder, ServerOperationKind, get_server_operation_lock


@pytest.mark.parametrize("busy", [False, True])
async def test_global_backup_records_success_or_skip_with_nested_file_scope(isolated_runtime, monkeypatch, busy):
    runtime = isolated_runtime
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
    snapshots = SimpleNamespace(create_snapshot=AsyncMock(return_value=SimpleNamespace(
        id="owned-snapshot", short_id="owned", summary=None,
    )))
    monkeypatch.setattr(backup, "_get_snapshot_service", lambda: snapshots)
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
        snapshots.create_snapshot.assert_not_awaited()
        assert any("跳过备份" in message for message in rows[0].messages)
    else:
        snapshots.create_snapshot.assert_awaited_once_with([runtime.settings.server_path])
