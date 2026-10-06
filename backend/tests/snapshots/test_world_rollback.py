import shutil

import pytest

from app.snapshots.restoration_models import RestorationType
from app.snapshots.scopes import WorldScope
from app.snapshots.selection_models import RestorationSelection
from tests.support.regions import chunk_value, region_bytes

from .support import complete, create, scope

pytestmark = [
    pytest.mark.binary("restic"),
    pytest.mark.binary("fd"),
    pytest.mark.binary("mcmap"),
]


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

