import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings
from app.dynamic_config.configs.world import WorldConfig
import app.world.layout as layout_module
from app.world.layout import (
    WorldRootPath,
    WorldLayoutDiscoveryError,
    WorldRoot,
    discover_world_root_paths,
    discover_world_roots,
    resolve_dimension_folder,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _write_properties(data_path: Path, level_name: str) -> None:
    (data_path / "server.properties").write_text(f"level-name={level_name}\n")


def _by_dimension_path(root: WorldRoot):
    return {
        d.region_dir.parent.relative_to(root.path).as_posix(): d
        for d in root.dimensions
    }


@pytest.mark.asyncio
async def test_vanilla_layout_with_three_dimensions():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")
        _touch(world / "entities" / "r.0.0.mca")
        _touch(world / "poi" / "r.0.0.mca")
        _touch(world / "DIM-1" / "region" / "r.0.0.mca")
        _touch(world / "DIM-1" / "entities" / "r.0.0.mca")
        _touch(world / "DIM-1" / "poi" / "r.0.0.mca")
        _touch(world / "DIM1" / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        root = roots[0]
        assert root.name == "world"
        assert root.path == world
        by_path = _by_dimension_path(root)
        assert set(by_path) == {".", "DIM-1", "DIM1"}
        assert by_path["."].region_dir == world / "region"
        assert by_path["."].entities_dir == world / "entities"
        assert by_path["."].poi_dir == world / "poi"
        assert by_path["DIM-1"].region_dir == world / "DIM-1" / "region"
        assert by_path["DIM-1"].entities_dir == world / "DIM-1" / "entities"
        assert by_path["DIM1"].region_dir == world / "DIM1" / "region"
        # End in this fixture has no entities/poi
        assert by_path["DIM1"].entities_dir is None
        assert by_path["DIM1"].poi_dir is None


@pytest.mark.asyncio
async def test_vanilla_dimension_directory_layout():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(
            world
            / "dimensions"
            / "minecraft"
            / "overworld"
            / "region"
            / "r.0.0.mca"
        )
        _touch(
            world
            / "dimensions"
            / "minecraft"
            / "the_nether"
            / "region"
            / "r.0.0.mca"
        )
        _touch(
            world
            / "dimensions"
            / "minecraft"
            / "the_end"
            / "region"
            / "r.0.0.mca"
        )

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        by_path = _by_dimension_path(roots[0])
        assert set(by_path) == {
            "dimensions/minecraft/overworld",
            "dimensions/minecraft/the_nether",
            "dimensions/minecraft/the_end",
        }
        assert by_path["dimensions/minecraft/overworld"].region_dir == (
            world / "dimensions" / "minecraft" / "overworld" / "region"
        )
        assert by_path["dimensions/minecraft/the_nether"].region_dir == (
            world / "dimensions" / "minecraft" / "the_nether" / "region"
        )
        assert by_path["dimensions/minecraft/the_end"].region_dir == (
            world / "dimensions" / "minecraft" / "the_end" / "region"
        )


@pytest.mark.asyncio
async def test_paper_multi_world_layout():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")

        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")

        nether_root = data_path / "world_nether"
        _touch(nether_root / "level.dat")
        _touch(nether_root / "DIM-1" / "region" / "r.0.0.mca")

        end_root = data_path / "world_the_end"
        _touch(end_root / "level.dat")
        _touch(end_root / "DIM1" / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)

        names = [r.name for r in roots]
        assert names == sorted(["world", "world_nether", "world_the_end"])

        by_name = {r.name: r for r in roots}
        assert list(_by_dimension_path(by_name["world"])) == ["."]
        assert list(_by_dimension_path(by_name["world_nether"])) == ["DIM-1"]
        assert list(_by_dimension_path(by_name["world_the_end"])) == ["DIM1"]


@pytest.mark.asyncio
async def test_pre_117_layout_has_no_entities_or_poi():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)
        assert len(roots) == 1
        overworld = roots[0].dimensions[0]
        assert overworld.region_dir == world / "region"
        assert overworld.entities_dir is None
        assert overworld.poi_dir is None


@pytest.mark.asyncio
async def test_legacy_custom_dimension_under_world_root():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")
        _touch(world / "DIM88" / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        by_path = _by_dimension_path(roots[0])
        assert set(by_path) == {".", "DIM88"}
        assert by_path["DIM88"].region_dir == world / "DIM88" / "region"


@pytest.mark.asyncio
async def test_custom_level_name():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "survival")
        world = data_path / "survival"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)
        assert len(roots) == 1
        assert roots[0].name == "survival"


@pytest.mark.asyncio
async def test_blank_level_name_falls_back_to_world():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, " ")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        assert roots[0].name == "world"


@pytest.mark.asyncio
async def test_missing_data_path_returns_empty():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        roots = await discover_world_roots(Path(tmp) / "does-not-exist")
        assert roots == []


@pytest.mark.asyncio
async def test_world_root_path_discovery_does_not_require_fd(monkeypatch):
    monkeypatch.setattr(settings, "fd_binary_path", Path("/missing/fd"))
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "survival")
        world = data_path / "survival"
        world.mkdir()

        roots = await discover_world_root_paths(data_path)

        assert roots == [WorldRootPath(name="survival", path=world)]


def test_resolve_dimension_folder_maps_direct_region_path():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "dimensions" / "modid" / "moon" / "region" / "r.0.0.mca")

        resolved = resolve_dimension_folder(
            data_path,
            WorldRootPath(name="world", path=world),
            "dimensions/modid/moon",
            exists_on_disk=False,
        )

        assert resolved.region_dir_relpath == "world/dimensions/modid/moon/region"
        assert resolved.exists_on_disk is True


def test_resolve_dimension_folder_rejects_unsafe_paths():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        world = data_path / "world"
        world.mkdir()

        resolved = resolve_dimension_folder(
            data_path,
            WorldRootPath(name="world", path=world),
            "../outside",
            exists_on_disk=True,
        )

        assert resolved.region_dir_relpath is None
        assert resolved.exists_on_disk is True


@pytest.mark.asyncio
async def test_deeply_nested_modded_dimensions():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")
        _touch(world / "DIM-1" / "region" / "r.0.0.mca")

        _touch(world / "dimensions" / "allthemodium" / "mining" / "region" / "r.0.0.mca")
        _touch(world / "dimensions" / "allthemodium" / "the_beyond" / "region" / "r.0.0.mca")
        _touch(world / "dimensions" / "ad_astra" / "moon" / "region" / "r.0.0.mca")

        # Non-dim siblings under the world root must not affect discovery.
        _touch(world / "playerdata" / "uuid.dat")
        _touch(world / "ftbchunks" / "data.snbt")

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        by_path = _by_dimension_path(roots[0])
        assert set(by_path) == {
            ".",
            "DIM-1",
            "dimensions/allthemodium/mining",
            "dimensions/allthemodium/the_beyond",
            "dimensions/ad_astra/moon",
        }

        assert by_path["dimensions/allthemodium/mining"].region_dir == (
            world / "dimensions" / "allthemodium" / "mining" / "region"
        )


@pytest.mark.asyncio
async def test_deep_ftb_team_dimension_layout():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        team_id = "2772fb19-2b8f-4cfd-b53a-b35d3ca41493"
        _touch(world / "level.dat")
        _touch(
            world
            / "dimensions"
            / "ftbteamdimensions"
            / "team"
            / team_id
            / "region"
            / "r.0.0.mca"
        )

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        dim = roots[0].dimensions[0]
        assert dim.region_dir == (
            world / "dimensions" / "ftbteamdimensions" / "team" / team_id / "region"
        )
        assert _by_dimension_path(roots[0]) == {
            f"dimensions/ftbteamdimensions/team/{team_id}": dim
        }


@pytest.mark.asyncio
async def test_walk_depth_bound_rejects_extreme_nesting():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")

        too_deep = world
        for i in range(WorldConfig().dimension_max_depth_from_world_root + 2):
            too_deep = too_deep / f"d{i}"
        _touch(too_deep / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)
        assert list(_by_dimension_path(roots[0])) == ["."]


@pytest.mark.asyncio
async def test_dimension_scan_depth_comes_from_config(monkeypatch):
    monkeypatch.setattr(
        layout_module,
        "config",
        SimpleNamespace(world=SimpleNamespace(dimension_max_depth_from_world_root=0)),
    )
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")
        _touch(world / "DIM88" / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        assert list(_by_dimension_path(roots[0])) == ["."]


@pytest.mark.asyncio
async def test_data_root_cache_dir_is_not_a_world_root():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")
        _touch(data_path / ".mcmap" / "palette.hash")

        roots = await discover_world_roots(data_path)
        assert len(roots) == 1
        assert roots[0].name == "world"
        assert list(_by_dimension_path(roots[0])) == ["."]


@pytest.mark.asyncio
async def test_region_mca_directory_is_not_a_dimension():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        (world / "region" / "r.0.0.mca").mkdir(parents=True)

        roots = await discover_world_roots(data_path)
        assert roots == []


@pytest.mark.asyncio
async def test_discover_world_roots_requires_fd(monkeypatch):
    monkeypatch.setattr(settings, "fd_binary_path", Path("/missing/fd"))
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "DIM88" / "region" / "r.0.0.mca")

        with pytest.raises(WorldLayoutDiscoveryError, match="fd command not found"):
            await discover_world_roots(data_path)
