import pytest

from app.operations.coordinator import ResourceClaim, ResourceKind
from app.servers.references import ServerRef
from app.world.events import SelectionResolutionError
from app.world.finalization import invalidate_map_cache
from app.world.models import RestorationType
from app.world.restore import WorldRestoreOrchestrator
from app.world.schemas import RestorationSelection


async def test_internal_world_alias_and_mca_link_claim_their_actual_targets(tmp_path):
    data = tmp_path / "srv1" / "data"
    region = data / "world" / "region"
    region.mkdir(parents=True)
    (data / "alias").symlink_to(region, target_is_directory=True)
    actual = data / "shared" / "r.0.0.mca"
    actual.parent.mkdir()
    actual.write_bytes(b"live")
    (region / actual.name).symlink_to(actual)
    reference = ServerRef("srv1", 7, tmp_path, data.parent, data)
    claims = await WorldRestoreOrchestrator._claims(reference, [data / "alias" / actual.name])
    for path in ("data/alias", "data/world/region", "data/shared/r.0.0.mca"):
        assert any(claim.covers(ResourceClaim(ResourceKind.FILES, "srv1", path)) for claim in claims)
    assert not any(claim.conflicts(ResourceClaim(ResourceKind.FILES, "srv1", "data/plugins/config.yml")) for claim in claims)


@pytest.mark.parametrize("scope", ["world", "mca"])
async def test_world_selection_rejects_symlink_targets_outside_data(tmp_path, scope):
    data = tmp_path / "srv1" / "data"
    region = data / "world" / "region"
    region.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "r.0.0.mca"
    target.write_bytes(b"not owned")
    if scope == "world":
        path = data / "escaped"
        path.symlink_to(outside, target_is_directory=True)
    else:
        path = region / target.name
        path.symlink_to(target)
    reference = ServerRef("srv1", 7, tmp_path, data.parent, data)
    with pytest.raises(SelectionResolutionError):
        await WorldRestoreOrchestrator._claims(reference, [path])
    assert target.read_bytes() == b"not owned"


@pytest.mark.parametrize("scope", [RestorationType.WORLD, RestorationType.DIMENSION])
async def test_interrupted_broad_restore_clears_tiles_before_file_events(tmp_path, scope):
    tiles = tmp_path / ".mcmap" / "tiles"
    for dimension in ("world/region", "world/DIM-1/region"):
        directory = tiles / dimension
        directory.mkdir(parents=True)
        (directory / "r.0.0.png").write_bytes(b"stale")
    selection = RestorationSelection(type=scope, region_dir_relpath="world/region" if scope == RestorationType.DIMENSION else None)
    await invalidate_map_cache(data_path=tmp_path, selection=selection, touched_items=[], uncertain=True)
    assert not (tiles / "world/region/r.0.0.png").exists()
    assert (tiles / "world/DIM-1/region/r.0.0.png").exists() == (scope == RestorationType.DIMENSION)
