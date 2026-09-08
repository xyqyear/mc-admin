"""Test that backup_cronjob skips when the per-server lock is already held."""

from datetime import UTC, datetime

import pytest

from app.cron.jobs.backup import BackupJobParams, backup_cronjob
from app.cron.types import ExecutionContext
from app.models import ExecutionStatus
from app.world import (
    GLOBAL_LOCK_KEY,
    LockHolder,
    ServerOperationKind,
    server_operation_lock,
)


def _make_context(params: BackupJobParams) -> ExecutionContext:
    return ExecutionContext(
        cronjob_id="cj-test",
        identifier="backup-test",
        execution_id="exec-test",
        params=params,
        started_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_backup_skips_when_server_lock_is_held():
    server_id = "lock-test-srv"
    holder = LockHolder(
        kind=ServerOperationKind.RESTORE,
        started_at=datetime.now(UTC),
        user_id=1,
        description="restore in progress",
    )

    params = BackupJobParams(server_id=server_id, keep_last=1)
    context = _make_context(params)

    async with server_operation_lock.acquire(server_id, holder):
        # Should return without raising and without invoking restic.
        await backup_cronjob(context)

    joined = "\n".join(context.messages)
    assert context.status == ExecutionStatus.SKIPPED
    assert "跳过备份" in joined
    assert server_id in joined
    assert "restore" in joined


@pytest.mark.asyncio
async def test_backup_skips_when_global_lock_is_held():
    holder = LockHolder(
        kind=ServerOperationKind.BACKUP,
        started_at=datetime.now(UTC),
        user_id=None,
        description="another backup",
    )

    params = BackupJobParams(keep_daily=1)
    context = _make_context(params)

    async with server_operation_lock.acquire(GLOBAL_LOCK_KEY, holder):
        await backup_cronjob(context)

    joined = "\n".join(context.messages)
    assert context.status == ExecutionStatus.SKIPPED
    assert "跳过备份" in joined
    assert GLOBAL_LOCK_KEY in joined


async def test_global_backup_skips_when_an_affected_server_is_restoring(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.cron.jobs import backup

    instance = Mock()
    instance.get_name.return_value = "affected"
    instance.get_project_path.return_value = tmp_path / "affected"
    instance.get_data_path.return_value = tmp_path / "affected" / "data"
    manager = Mock()
    manager.get_all_instances = AsyncMock(return_value=[instance])
    monkeypatch.setattr(backup, "docker_mc_manager", manager)
    monkeypatch.setattr(backup, "settings", SimpleNamespace(server_path=tmp_path))
    snapshots = Mock()
    snapshots.create_snapshot = AsyncMock()
    monkeypatch.setattr(backup, "_get_snapshot_service", lambda: snapshots)
    holder = LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), None, "restoring")
    context = _make_context(BackupJobParams(keep_last=1))
    async with server_operation_lock.acquire("affected", holder):
        await backup_cronjob(context)
        assert not server_operation_lock.is_locked(GLOBAL_LOCK_KEY)
    snapshots.create_snapshot.assert_not_awaited()
    assert context.status == ExecutionStatus.SKIPPED
    assert any("跳过备份" in message for message in context.messages)
