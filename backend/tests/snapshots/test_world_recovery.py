import asyncio
import shutil
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.background_tasks import TaskStatus
from app.runtime_resources import current_runtime
from app.snapshots.restoration_models import RestorationStatus, RestorationType
from app.snapshots.scopes import WorldScope
from app.snapshots.selection_models import RestorationSelection
from tests.support.regions import chunk_value, region_bytes

from .test_commands import complete
from .test_world_commands import scope

pytestmark = [
    pytest.mark.binary("restic"),
    pytest.mark.binary("fd"),
    pytest.mark.binary("mcmap"),
]


async def create(case, target=None):
    return (await complete(case, await case.commands.create(target or scope(), 1)))[
        "snapshot"
    ]["id"]


@pytest.mark.parametrize("kind", ["world", "dimension", "regions", "chunks"])
async def test_empty_source_removes_selected_data_and_remains_reversible(
    world_case, kind
):
    case = world_case
    live = case.region / "r.0.0.mca"
    live.unlink()
    source = (await case.snapshots.create_snapshot([case.region.parent])).id
    live.write_bytes(region_bytes(["live zero", "live one"]))
    restore = await case.commands.restore(scope(kind), source, 1)
    await complete(case, restore)
    if kind == "chunks":
        assert chunk_value(live, 0) is None
        assert chunk_value(live, 1) == "live one"
    else:
        assert not live.exists()
    rollback = await case.commands.rollback(restore["restoration_id"], 1)
    await complete(case, rollback)
    assert chunk_value(live, 0) == "live zero"
    assert chunk_value(live, 1) == "live one"
    undo = await case.commands.rollback(rollback["restoration_id"], 1)
    await complete(case, undo)
    assert chunk_value(live, 0) is None if kind == "chunks" else not live.exists()
    assert not list(case.data.rglob(".mc-admin-absence-*"))


@pytest.mark.parametrize("kind", ["world", "dimension", "regions", "chunks"])
async def test_rollback_recreates_missing_world_and_can_restore_its_absence(
    world_case, kind
):
    case = world_case
    source = await create(case)
    restore = await case.commands.restore(scope(kind), source, 1)
    await complete(case, restore)
    shutil.rmtree(case.region.parent)
    rollback = await case.commands.rollback(restore["restoration_id"], 1)
    await complete(case, rollback)
    assert chunk_value(case.region / "r.0.0.mca", 0) == "source zero"
    await complete(case, await case.commands.rollback(rollback["restoration_id"], 1))
    assert not case.region.parent.exists()
    assert not list(case.data.rglob(".mc-admin-absence-*"))


async def test_dimension_snapshot_records_absence_and_legacy_sources_preserve_unknown_data(
    world_case,
):
    case = world_case
    legacy = await case.snapshots.create_snapshot([case.region])
    source = await create(case, scope("dimension"))
    entities = case.region.parent / "entities"
    entities.mkdir()
    live = entities / "r.0.0.mca"
    live.write_bytes(region_bytes(["new entities"]))
    eligible = await case.commands.eligible(scope("dimension"))
    assert source in [item.id for item in eligible]
    legacy_restore = await case.commands.restore(scope("dimension"), legacy.id, 1)
    result = await complete(case, legacy_restore)
    assert chunk_value(live, 0) == "new entities"
    assert str(entities) in result["skipped_paths"]
    restored = await case.commands.restore(scope("dimension"), source, 1)
    await complete(case, restored)
    assert not entities.exists()
    await complete(case, await case.commands.rollback(restored["restoration_id"], 1))
    assert chunk_value(live, 0) == "new entities"


@pytest.mark.parametrize("kind", ["world", "dimension", "regions"])
async def test_scope_preserves_other_dimensions_regions_and_server_files(
    world_case, kind
):
    case = world_case
    world = case.region.parent
    nether = world / "DIM-1" / "region"
    creative = case.data / "world_creative" / "region"
    for folder in [nether, creative]:
        folder.mkdir(parents=True)
        (folder / "r.0.0.mca").write_bytes(region_bytes(["source other"]))
    (creative.parent / "level.dat").write_bytes(b"creative world")
    other = case.region / "r.1.0.mca"
    other.write_bytes(region_bytes(["source neighbor"]))
    config = case.data / "config.yml"
    config.write_bytes(b"server configuration")
    source = await create(case)
    for path in [
        case.region / "r.0.0.mca",
        other,
        nether / "r.0.0.mca",
        creative / "r.0.0.mca",
    ]:
        path.write_bytes(region_bytes(["live data"]))
    await complete(case, await case.commands.restore(scope(kind), source, 1))
    assert chunk_value(case.region / "r.0.0.mca", 0) == "source zero"
    assert chunk_value(other, 0) == (
        "live data" if kind == "regions" else "source neighbor"
    )
    for folder in [nether, creative]:
        assert chunk_value(folder / "r.0.0.mca", 0) == (
            "source other" if kind == "world" else "live data"
        )
    assert config.read_bytes() == b"server configuration"


@pytest.mark.parametrize("kind", ["regions", "chunks"])
async def test_safety_snapshot_is_eligible_without_speculative_overflow_files(
    world_case, kind
):
    case = world_case
    source = await create(case)
    accepted = await case.commands.restore(scope(kind), source, 1)
    result = await complete(case, accepted)
    assert result["safety_snapshot_id"] in [
        item.id for item in await case.commands.eligible(scope(kind))
    ]
    other = WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType.REGIONS,
            region_dir_relpath="world/region",
            regions=[(1, 0)],
        ),
    )
    assert result["safety_snapshot_id"] not in [
        item.id for item in await case.commands.eligible(other)
    ]


async def test_world_source_exclusions_survive_configuration_change_and_rollback(
    world_case,
):
    case = world_case
    case.config.snapshots.ignored_paths = ["<LEVEL_NAME>/ignored_cache"]
    ignored = case.region.parent / "ignored_cache"
    ignored.mkdir()
    (ignored / "tile").write_bytes(b"original cache")
    source = await create(case)
    case.config.snapshots.ignored_paths = []
    (ignored / "tile").write_bytes(b"new cache")
    (ignored / "new").write_bytes(b"new file")
    extra = case.region.parent / "extraneous.dat"
    extra.write_bytes(b"remove this")
    accepted = await case.commands.restore(scope(), source, 1)
    await complete(case, accepted)
    assert not extra.exists()
    for operation in [None, accepted["restoration_id"]]:
        if operation:
            await complete(case, await case.commands.rollback(operation, 1))
        assert (ignored / "tile").read_bytes() == b"new cache"
        assert (ignored / "new").read_bytes() == b"new file"


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
    holder = current_runtime().resource("server_operation_lock").get_holder("survival")
    assert holder and holder.user_id == 7 and holder.restoration_id == row.id
    assert await case.tasks.cancel(accepted["task_id"])
    await asyncio.wait_for(case.tasks.get_future(accepted["task_id"]), 10)
    assert case.tasks.get_task(accepted["task_id"]).status is TaskStatus.CANCELLED
    row = await case.commands.store.get(row.id)
    assert row.status is RestorationStatus.CANCELLED and row.finished_at
    assert (case.region / "r.0.0.mca").read_bytes() == original
    assert not current_runtime().resource("server_operation_lock").is_locked("survival")


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
    assert not current_runtime().resource("server_operation_lock").is_locked("survival")
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
        assert current_runtime().resource("server_operation_lock").is_locked("survival")
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
    assert not current_runtime().resource("server_operation_lock").is_locked("survival")
    await complete(case, await case.commands.rollback(row.id, 1))
    assert chunk_value(live, 0) == "live before recovery"
