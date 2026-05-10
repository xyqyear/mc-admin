"""Test that backup_cronjob skips when the per-server lock is already held."""

from datetime import datetime, timezone

import pytest

from app.cron.jobs.backup import BackupJobParams, backup_cronjob
from app.cron.types import ExecutionContext
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
        started_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_backup_skips_when_server_lock_is_held():
    server_id = "lock-test-srv"
    holder = LockHolder(
        kind=ServerOperationKind.RESTORE,
        started_at=datetime.now(timezone.utc),
        user_id=1,
        description="restore in progress",
    )

    params = BackupJobParams(server_id=server_id, keep_last=1)
    context = _make_context(params)

    async with server_operation_lock.acquire(server_id, holder):
        # Should return without raising and without invoking restic.
        await backup_cronjob(context)

    joined = "\n".join(context.messages)
    assert "跳过备份" in joined
    assert server_id in joined
    assert "restore" in joined


@pytest.mark.asyncio
async def test_backup_skips_when_global_lock_is_held():
    holder = LockHolder(
        kind=ServerOperationKind.BACKUP,
        started_at=datetime.now(timezone.utc),
        user_id=None,
        description="another backup",
    )

    params = BackupJobParams(keep_daily=1)
    context = _make_context(params)

    async with server_operation_lock.acquire(GLOBAL_LOCK_KEY, holder):
        await backup_cronjob(context)

    joined = "\n".join(context.messages)
    assert "跳过备份" in joined
    assert GLOBAL_LOCK_KEY in joined
