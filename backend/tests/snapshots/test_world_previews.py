import zlib

import pytest

from app.dynamic_config.configs.mcmap import MCMapConfig
from app.runtime_resources import current_runtime
from app.snapshots.restoration_models import RestorationType
from app.snapshots.scopes import WorldScope
from app.snapshots.selection_models import RestorationSelection

from .test_commands import complete

pytestmark = [pytest.mark.binary("restic"), pytest.mark.binary("fd"), pytest.mark.binary("mcmap")]


@pytest.mark.parametrize("kind", ["regions", "chunks"])
async def test_map_preview_preserves_source_protected_and_unselected_external_chunks(world_case, kind):
    case = world_case
    case.config.mcmap = MCMapConfig()
    case.config.snapshots.ignored_paths = [".mcmap", "world/region/c.0.0.mcc"]
    header = bytearray(8192)
    for chunk in range(3):
        header[chunk * 4:chunk * 4 + 4] = ((chunk + 2) << 8 | 1).to_bytes(4)
    mca = case.region / "r.0.0.mca"
    mca.write_bytes(bytes(header) + b"\x00\x00\x00\x01\x82".ljust(4096, b"\0") * 3)
    for chunk in range(3):
        (case.region / f"c.{chunk}.0.mcc").write_bytes(zlib.compress(f"source {chunk}".encode()))
    source = await complete(case, await case.commands.create(WorldScope(server_id="survival", selection=RestorationSelection(type=RestorationType.WORLD)), 1))
    for chunk in range(3):
        (case.region / f"c.{chunk}.0.mcc").write_bytes(zlib.compress(f"live {chunk}".encode()))
    case.config.snapshots.ignored_paths = [".mcmap"]
    cache = case.data / ".mcmap"
    cache.mkdir()
    (cache / "palette.json").write_text("{}")
    scope = WorldScope(server_id="survival", selection=RestorationSelection(type=RestorationType(kind), region_dir_relpath="world/region", regions=[(0, 0)] if kind == "regions" else [], chunks=[(0, 0), (1, 0)] if kind == "chunks" else []))
    previews = current_runtime().resource("snapshot_previews")
    result = await complete(case, await previews.submit(scope, source["snapshot"]["id"], 1))
    assert result["kind"] == "map" and result["skipped_count"] > 0
    directory = previews.manager.get_session_dir(result["preview_id"])
    staged = case.snapshots.stage_destination(directory / ("preview" if kind == "chunks" else "source"), case.region)
    assert zlib.decompress((staged / "c.0.0.mcc").read_bytes()) == b"live 0"
    assert zlib.decompress((staged / "c.1.0.mcc").read_bytes()) == b"source 1"
    assert zlib.decompress((staged / "c.2.0.mcc").read_bytes()) == (b"live 2" if kind == "chunks" else b"source 2")
    assert [zlib.decompress((case.region / f"c.{chunk}.0.mcc").read_bytes()) for chunk in range(3)] == [b"live 0", b"live 1", b"live 2"]
    assert mca.read_bytes() == bytes(header) + b"\x00\x00\x00\x01\x82".ljust(4096, b"\0") * 3
    await complete(case, await previews.end(result["preview_id"], 1))
    assert not directory.exists()
