import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.background_tasks import TaskStatus
from app.runtime_resources import current_runtime
from app.snapshots.restoration_models import RestorationStatus
from tests.support.regions import chunk_value, region_bytes

from .support import complete, create, scope

pytestmark = [
    pytest.mark.binary("restic"),
    pytest.mark.binary("fd"),
    pytest.mark.binary("mcmap"),
]


@pytest.mark.parametrize("kind", ["world", "dimension", "regions", "chunks"])
async def test_safety_persists_before_writes_and_cancel_retains_recovery(
    world_case, monkeypatch, kind
):
    case = world_case
    source = await create(case)
    original = (case.region / "r.0.0.mca").read_bytes()
    ready = asyncio.Event()

    async def paused(*args, **kwargs):
        ready.set()
        await asyncio.Event().wait()
        yield

    monkeypatch.setattr(
        case.snapshots, "stage" if kind == "chunks" else "restore", paused
    )
    accepted = await case.commands.restore(scope(kind), source, 7)
    await asyncio.wait_for(ready.wait(), 30)
    row = await case.commands.store.get(accepted["restoration_id"])
    assert row and row.status is RestorationStatus.RUNNING and row.safety_snapshot_id
    assert row.operation_id == accepted["task_id"] and row.server_generation
    assert row.safety_snapshot_id in [
        item.id for item in await case.snapshots.list_snapshots()
    ]
    holder = current_runtime().server_operation_lock.get_holder("survival")
    assert holder and holder.user_id == 7 and holder.restoration_id == row.id
    assert await case.tasks.cancel(accepted["task_id"])
    await asyncio.wait_for(case.tasks.get_future(accepted["task_id"]), 10)
    assert case.tasks.get_task(accepted["task_id"]).status is TaskStatus.CANCELLED
    row = await case.commands.store.get(row.id)
    assert row.status is RestorationStatus.CANCELLED and row.finished_at
    assert (case.region / "r.0.0.mca").read_bytes() == original
    assert not current_runtime().server_operation_lock.is_locked("survival")


@pytest.mark.parametrize("fault", ["write", "cache"])
async def test_world_failure_keeps_history_recoverable_and_reports_degraded_cache(
    world_case, monkeypatch, fault
):
    case = world_case
    source = await create(case)
    live = case.region / "r.0.0.mca"
    live.write_bytes(region_bytes(["live data"]))
    tiles = case.data / ".mcmap" / "tiles" / "world" / "region"
    tiles.mkdir(parents=True)
    tile = tiles / "r.0.0.png"
    tile.write_bytes(b"stale cache")
    if fault == "write":

        async def failed(*args, **kwargs):
            raise RuntimeError("private error")
            yield

        monkeypatch.setattr(case.snapshots, "restore", failed)
    else:
        monkeypatch.setattr(
            "app.snapshots.file_restore.invalidate_map_cache",
            AsyncMock(side_effect=OSError("private cache error")),
        )
    accepted = await case.commands.restore(scope(), source, 1)
    await complete(case, accepted, success=False)
    row = await case.commands.store.get(accepted["restoration_id"])
    operation = await case.journal.get(accepted["task_id"])
    assert (
        row
        and row.status is RestorationStatus.FAILED
        and row.finished_at
        and row.safety_snapshot_id
    )
    assert row.error_message and "private" not in row.error_message
    assert (
        operation
        and operation.writers_stopped
        and operation.cache_degraded == (fault == "cache")
    )
    assert not current_runtime().server_operation_lock.is_locked("survival")
    if fault == "cache":
        assert "数据已恢复，但地图缓存更新失败" in row.error_message
        assert chunk_value(live, 0) == "source zero"
    else:
        assert chunk_value(live, 0) == "live data"
        assert not tile.exists()


async def test_cancel_during_cache_finalization_waits_for_cleanup_and_preserves_rollback(
    world_case, monkeypatch
):
    case = world_case
    source = await create(case)
    live = case.region / "r.0.0.mca"
    live.write_bytes(region_bytes(["live before recovery"]))
    tiles = case.data / ".mcmap" / "tiles" / "world" / "region"
    tiles.mkdir(parents=True)
    affected, unrelated = tiles / "r.0.0.png", tiles / "r.7.7.png"
    affected.write_bytes(b"stale")
    unrelated.write_bytes(b"unrelated")
    entered, release = asyncio.Event(), asyncio.Event()
    invalidate = case.commands._files.invalidate

    async def gated(*args, **kwargs):
        entered.set()
        await release.wait()
        await invalidate(*args, **kwargs)

    monkeypatch.setattr(case.commands._files, "invalidate", gated)
    accepted = await case.commands.restore(scope("regions"), source, 1)
    future = case.tasks.get_future(accepted["task_id"])
    assert future is not None
    try:
        await asyncio.wait_for(entered.wait(), 30)
        assert chunk_value(live, 0) == "source zero"
        row = await case.commands.store.get(accepted["restoration_id"])
        assert row and row.safety_snapshot_id
        assert await case.tasks.cancel(accepted["task_id"])
        assert future is not None and not future.done()
        assert current_runtime().server_operation_lock.is_locked("survival")
        with pytest.raises(HTTPException):
            case.commands.require_deletable("survival")
    finally:
        release.set()
        assert future is not None
        await asyncio.wait_for(future, 10)
    assert case.tasks.get_task(accepted["task_id"]).status is TaskStatus.CANCELLED
    row = await case.commands.store.get(accepted["restoration_id"])
    assert row.status is RestorationStatus.CANCELLED and row.safety_snapshot_id
    assert not affected.exists() and unrelated.read_bytes() == b"unrelated"
    assert not current_runtime().server_operation_lock.is_locked("survival")
    await complete(case, await case.commands.rollback(row.id, 1))
    assert chunk_value(live, 0) == "live before recovery"

