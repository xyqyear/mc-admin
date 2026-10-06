import shutil

import pytest

from app.snapshots.restoration_models import RestorationType
from app.snapshots.scopes import WorldScope
from app.snapshots.selection_models import RestorationSelection
from tests.support.regions import chunk_value, region_bytes

from .support import complete, scope

pytestmark = [
    pytest.mark.binary("restic"),
    pytest.mark.binary("fd"),
    pytest.mark.binary("mcmap"),
]


@pytest.mark.parametrize("kind", ["world", "dimension", "regions", "chunks"])
async def test_world_tasks_restore_and_rollback_missing_sidecars(world_case, kind):
    case = world_case
    for sub in ["entities", "poi"]:
        folder = case.region.parent / sub
        folder.mkdir()
        (folder / "r.0.0.mca").write_bytes(region_bytes(["source zero", "source one"]))
    source = await complete(case, await case.commands.create(scope(), 1))
    for sub in ["entities", "poi"]:
        shutil.rmtree(case.region.parent / sub)
    (case.region / "r.0.0.mca").write_bytes(region_bytes(["live zero", "live one"]))
    accepted = await case.commands.restore(scope(kind), source["snapshot"]["id"], 1)
    await complete(case, accepted)
    assert chunk_value(case.region / "r.0.0.mca", 0) == "source zero"
    assert chunk_value(case.region / "r.0.0.mca", 1) == (
        "live one" if kind == "chunks" else "source one"
    )
    assert (
        chunk_value(case.region.parent / "entities" / "r.0.0.mca", 0) == "source zero"
    )
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert chunk_value(case.region / "r.0.0.mca", 0) == "live zero"
    assert not (case.region.parent / "entities").exists()
    assert not (case.region.parent / "poi").exists()


async def test_chunk_protection_preserves_ignored_sidecars_and_unselected_data(
    world_case,
):
    case = world_case
    entities = case.region.parent / "entities"
    entities.mkdir()
    (entities / "r.0.0.mca").write_bytes(
        region_bytes(["source entity", "other entity"])
    )
    source = await complete(case, await case.commands.create(scope(), 1))
    (entities / "r.0.0.mca").write_bytes(
        region_bytes(["protected entity", "protected sibling"])
    )
    protected = (entities / "r.0.0.mca").read_bytes()
    (case.region / "r.0.0.mca").write_bytes(
        region_bytes(["protected terrain", "restorable terrain"])
    )
    case.config.snapshots.ignored_paths = ["world/entities", "world/region/c.0.0.mcc"]
    selection = WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType.CHUNKS,
            region_dir_relpath="world/region",
            chunks=[(0, 0), (1, 0)],
        ),
    )
    accepted = await case.commands.restore(selection, source["snapshot"]["id"], 1)
    await complete(case, accepted)
    assert (entities / "r.0.0.mca").read_bytes() == protected
    assert chunk_value(case.region / "r.0.0.mca", 0) == "protected terrain"
    assert chunk_value(case.region / "r.0.0.mca", 1) == "source one"
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert chunk_value(case.region / "r.0.0.mca", 0) == "protected terrain"
    assert chunk_value(case.region / "r.0.0.mca", 1) == "restorable terrain"
    assert (entities / "r.0.0.mca").read_bytes() == protected


async def test_mcc_only_world_change_invalidates_its_tile_despite_cache_exclusion(
    world_case,
):
    case = world_case
    sidecar = case.region / "c.-33.-1.mcc"
    sidecar.write_bytes(b"snapshot overflow")
    case.config.snapshots.ignored_paths = [".mcmap"]
    source = await complete(case, await case.commands.create(scope(), 1))
    sidecar.write_bytes(b"new overflow")
    tiles = case.data / ".mcmap" / "tiles" / "world" / "region"
    tiles.mkdir(parents=True)
    changed = tiles / "r.-2.-1.png"
    untouched = tiles / "r.0.0.png"
    changed.write_bytes(b"stale overflow tile")
    untouched.write_bytes(b"unchanged terrain tile")
    palette = case.data / ".mcmap" / "palette.json"
    palette.write_bytes(b"retained palette")
    await complete(
        case, await case.commands.restore(scope(), source["snapshot"]["id"], 1)
    )
    assert sidecar.read_bytes() == b"snapshot overflow"
    assert not changed.exists()
    assert untouched.read_bytes() == b"unchanged terrain tile"
    assert palette.read_bytes() == b"retained palette"


@pytest.mark.parametrize("kind", ["regions", "chunks"])
async def test_negative_cross_region_external_chunks_restore_and_rollback(
    world_case, kind
):
    import zlib

    case = world_case
    for filename, index in [("r.-2.-1.mca", 1023), ("r.1.0.mca", 0)]:
        header = bytearray(8192)
        header[index * 4 : index * 4 + 4] = b"\x00\x00\x02\x01"
        (case.region / filename).write_bytes(
            bytes(header) + b"\x00\x00\x00\x01\x82".ljust(4096, b"\0")
        )
    sidecars = [case.region / "c.-33.-1.mcc", case.region / "c.32.0.mcc"]
    for path in sidecars:
        path.write_bytes(zlib.compress(b"source external chunk"))
    source = await complete(case, await case.commands.create(scope(), 1))
    for path in sidecars:
        path.write_bytes(zlib.compress(b"live external chunk"))
    neighbor = (case.region / "r.0.0.mca").read_bytes()
    tile_dir = case.data / ".mcmap" / "tiles" / "world" / "region"
    tile_dir.mkdir(parents=True)
    for name in ["r.-2.-1.png", "r.1.0.png", "r.0.0.png"]:
        (tile_dir / name).write_bytes(b"cached tile")
    palette = case.data / ".mcmap" / "palette.json"
    jar = case.data / ".mcmap" / "client.jar"
    palette.write_bytes(b"palette")
    jar.write_bytes(b"jar")
    selection = WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType(kind),
            region_dir_relpath="world/region",
            regions=[(-2, -1), (1, 0)] if kind == "regions" else [],
            chunks=[(-33, -1), (32, 0)] if kind == "chunks" else [],
        ),
    )
    accepted = await case.commands.restore(selection, source["snapshot"]["id"], 1)
    await complete(case, accepted)
    for path in sidecars:
        assert zlib.decompress(path.read_bytes()) == b"source external chunk"
    assert not (tile_dir / "r.-2.-1.png").exists()
    assert not (tile_dir / "r.1.0.png").exists()
    assert (tile_dir / "r.0.0.png").read_bytes() == b"cached tile"
    assert (case.region / "r.0.0.mca").read_bytes() == neighbor
    assert palette.read_bytes() == b"palette" and jar.read_bytes() == b"jar"
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    for path in sidecars:
        assert zlib.decompress(path.read_bytes()) == b"live external chunk"
    assert (case.region / "r.0.0.mca").read_bytes() == neighbor
