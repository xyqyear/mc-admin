import pytest

from tests.support.regions import chunk_value, region_bytes

from .support import complete, create, scope

pytestmark = [
    pytest.mark.binary("restic"),
    pytest.mark.binary("fd"),
    pytest.mark.binary("mcmap"),
]


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

