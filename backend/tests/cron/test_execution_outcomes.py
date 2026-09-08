import asyncio
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cron import crud
from app.cron.jobs import backup
from app.cron.manager import CronManager
from app.models import Base, ExecutionStatus
from app.world import (
    GLOBAL_LOCK_KEY,
    LockHolder,
    ServerOperationKind,
    server_operation_lock,
)


@pytest.fixture
async def execution_manager(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cron.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn,
                    tables=[
                        Base.metadata.tables[name]
                        for name in ("cronjob", "cronjob_execution")
                    ],
                )
            )
        monkeypatch.setattr("app.cron.manager.get_async_session", sessions)
        async with sessions() as session:
            await crud.create_cronjob(
                session,
                cronjob_id="outcome-test",
                identifier="backup",
                name="备份结果测试",
                cron="0 0 * * *",
                params_json='{"enable_forget": false}',
            )
        yield CronManager()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("server_id", [None, "busy-server"])
async def test_locked_backup_persists_skipped_history(
    execution_manager, monkeypatch, server_id
):
    snapshots = Mock()
    monkeypatch.setattr(backup, "_get_snapshot_service", snapshots)
    holder = LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), None, "恢复中")
    async with server_operation_lock.acquire(server_id or GLOBAL_LOCK_KEY, holder):
        await execution_manager._execute_cronjob_wrapper(
            "outcome-test",
            "backup",
            backup.BackupJobParams(server_id=server_id, enable_forget=False),
            backup.backup_cronjob,
        )

    snapshots.assert_not_called()
    rows = await CronManager().get_execution_history("outcome-test")
    assert len(rows) == 1
    assert rows[0].status == ExecutionStatus.SKIPPED
    assert rows[0].ended_at is not None
    assert rows[0].duration_ms is not None
    assert any("跳过备份" in message and "恢复中" in message for message in rows[0].messages)
    job = await execution_manager.get_cronjob_config("outcome-test")
    assert job is not None and job.execution_count == 1


@pytest.mark.parametrize("outcome", ["completed", "failed", "cancelled"])
async def test_execution_preserves_other_terminal_outcomes(execution_manager, outcome):
    async def job(context):
        if outcome == "failed":
            raise RuntimeError("备份失败")
        if outcome == "cancelled":
            raise asyncio.CancelledError
        context.log("备份完成")

    execution = execution_manager._execute_cronjob_wrapper(
        "outcome-test", "backup", backup.BackupJobParams(enable_forget=False), job
    )
    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await execution
    else:
        await execution

    rows = await execution_manager.get_execution_history("outcome-test")
    assert len(rows) == 1
    assert rows[0].status == ExecutionStatus(outcome)
    assert rows[0].ended_at is not None
