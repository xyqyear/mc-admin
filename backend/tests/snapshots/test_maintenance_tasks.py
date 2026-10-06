import asyncio

import pytest
from fastapi import HTTPException

from app.runtime_resources import current_runtime
from app.snapshots.maintenance import SnapshotMaintenance

from .support import complete
from .test_previews import prepared

pytestmark = pytest.mark.binary("restic")


async def test_accepted_delete_reserves_repository_until_actual_completion(case, monkeypatch):
    _, scope, source = await prepared(case)
    started, release = asyncio.Event(), asyncio.Event()
    original = case.client.forget_id
    async def pause(*args, **kwargs):
        started.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(case.client, "forget_id", pause)
    commands = SnapshotMaintenance(case.snapshots, case.tasks)
    accepted = await asyncio.wait_for(commands.submit(1, snapshot_id=source), 2)
    await asyncio.wait_for(started.wait(), 5)
    assert case.tasks.get_task(accepted["task_id"]).status.value == "running"
    with pytest.raises(HTTPException) as error:
        await case.commands.create(scope, 1)
    assert error.value.status_code == 423
    previews = current_runtime().snapshot_previews
    assert previews is not None
    with pytest.raises(HTTPException):
        await previews.submit(scope, source, 1)
    assert source in {snapshot.id for snapshot in await case.snapshots.list_snapshots()}
    release.set()
    result = await complete(case, accepted)
    assert "已删除" in result["message"]
    assert source not in {snapshot.id for snapshot in await case.snapshots.list_snapshots()}
    await complete(case, await case.commands.create(scope, 1))


async def test_cleanup_waits_for_active_preview_reader_before_releasing_source(case):
    _, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    preview_id = (await complete(case, await previews.submit(scope, source, 1)))["preview_id"]
    directory = previews.manager.get_session_dir(preview_id)
    assert directory is not None
    async with previews.manager.use(preview_id):
        accepted = await previews.end(preview_id, 1)
        task = case.tasks.get_task(accepted["task_id"])
        for _ in range(200):
            task = case.tasks.get_task(accepted["task_id"])
            if task.status.value == "running":
                break
            await asyncio.sleep(0.01)
        assert task.status.value == "running" and directory.exists()
        with pytest.raises(HTTPException):
            await SnapshotMaintenance(case.snapshots, case.tasks).submit(1, snapshot_id=source)
    await complete(case, accepted)
    assert not directory.exists()
    await complete(case, await SnapshotMaintenance(case.snapshots, case.tasks).submit(1, snapshot_id=source))


async def test_cron_retention_skips_active_preview_without_deleting_its_source(case):
    from app.cron import crud
    from app.cron.jobs.backup import BackupJobParams, backup_cronjob
    from app.cron.manager import CronManager
    from app.cron.models import ExecutionStatus
    from app.operations.journal_types import OperationState

    _, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    preview_id = (await complete(case, await previews.submit(scope, source, 1)))["preview_id"]
    async with current_runtime().database.session_factory() as session:
        await crud.create_cronjob(session, cronjob_id="preview-retention", identifier="backup", name="保留策略", cron="0 0 * * *", params_json='{"enable_forget":true,"keep_last":1}')
    manager = CronManager()
    await manager._execute_cronjob_wrapper("preview-retention", "backup", BackupJobParams(keep_last=1), backup_cronjob)
    history = await manager.get_execution_history("preview-retention")
    assert len(history) == 1 and history[0].status is ExecutionStatus.SKIPPED
    assert any("快照已创建，跳过保留策略清理" in message for message in history[0].messages)
    saved = await case.snapshots.list_snapshots()
    assert len(saved) == 2 and source in {snapshot.id for snapshot in saved}
    records = [row for row in await case.journal.list() if row.kind == "cron_backup"]
    assert len(records) == 1 and records[0].state is OperationState.SKIPPED
    assert records[0].writers_stopped and not records[0].processes
    await complete(case, await previews.end(preview_id, 1))


async def test_cron_skips_repository_maintenance_without_creating_failed_backup(case):
    from app.cron import crud
    from app.cron.jobs.backup import BackupJobParams, backup_cronjob
    from app.cron.manager import CronManager
    from app.cron.models import ExecutionStatus
    from app.operations.journal_types import OperationState

    async with current_runtime().database.session_factory() as session:
        await crud.create_cronjob(session, cronjob_id="busy-repository", identifier="backup", name="仓库维护期间备份", cron="0 0 * * *", params_json='{"enable_forget":false}')
    manager = CronManager()
    with case.snapshots.repository_use.maintain():
        await manager._execute_cronjob_wrapper("busy-repository", "backup", BackupJobParams(enable_forget=False), backup_cronjob)
    history = await manager.get_execution_history("busy-repository")
    assert len(history) == 1 and history[0].status is ExecutionStatus.SKIPPED
    assert any("快照仓库正在维护" in message for message in history[0].messages)
    assert await case.snapshots.list_snapshots() == []
    records = [row for row in await case.journal.list() if row.kind == "cron_backup"]
    assert len(records) == 1 and records[0].state is OperationState.SKIPPED
