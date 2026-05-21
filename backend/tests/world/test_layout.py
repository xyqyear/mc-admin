import tempfile
from pathlib import Path

import pytest

from app.config import settings
from app.world.dimension_labels import (
    END_LABEL,
    NETHER_LABEL,
    OVERWORLD_LABEL,
)
from app.world.layout import (
    DIMENSION_MAX_DEPTH_FROM_WORLD_ROOT,
    WorldLayoutDiscoveryError,
    discover_world_roots,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _write_properties(data_path: Path, level_name: str) -> None:
    (data_path / "server.properties").write_text(f"level-name={level_name}\n")


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
        labels = [d.label for d in root.dimensions]
        assert sorted(labels) == sorted([OVERWORLD_LABEL, NETHER_LABEL, END_LABEL])

        by_label = {d.label: d for d in root.dimensions}
        assert by_label[OVERWORLD_LABEL].region_dir == world / "region"
        assert by_label[OVERWORLD_LABEL].entities_dir == world / "entities"
        assert by_label[OVERWORLD_LABEL].poi_dir == world / "poi"
        assert by_label[NETHER_LABEL].region_dir == world / "DIM-1" / "region"
        assert by_label[NETHER_LABEL].entities_dir == world / "DIM-1" / "entities"
        assert by_label[END_LABEL].region_dir == world / "DIM1" / "region"
        # End in this fixture has no entities/poi
        assert by_label[END_LABEL].entities_dir is None
        assert by_label[END_LABEL].poi_dir is None


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
        by_label = {d.label: d for d in roots[0].dimensions}
        assert set(by_label) == {OVERWORLD_LABEL, NETHER_LABEL, END_LABEL}
        assert by_label[OVERWORLD_LABEL].region_dir == (
            world / "dimensions" / "minecraft" / "overworld" / "region"
        )
        assert by_label[NETHER_LABEL].region_dir == (
            world / "dimensions" / "minecraft" / "the_nether" / "region"
        )
        assert by_label[END_LABEL].region_dir == (
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
        assert [d.label for d in by_name["world"].dimensions] == [OVERWORLD_LABEL]
        assert [d.label for d in by_name["world_nether"].dimensions] == [NETHER_LABEL]
        assert [d.label for d in by_name["world_the_end"].dimensions] == [END_LABEL]


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
        assert overworld.label == OVERWORLD_LABEL
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
        by_label = {d.label: d for d in roots[0].dimensions}
        assert set(by_label) == {OVERWORLD_LABEL, "DIM88"}
        assert by_label["DIM88"].region_dir == world / "DIM88" / "region"


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
        labels = {d.label for d in roots[0].dimensions}
        assert labels == {
            OVERWORLD_LABEL,
            NETHER_LABEL,
            "allthemodium/mining",
            "allthemodium/the_beyond",
            "ad_astra/moon",
        }

        by_label = {d.label: d for d in roots[0].dimensions}
        assert by_label["allthemodium/mining"].region_dir == (
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
        assert dim.label == f"ftbteamdimensions/team/{team_id}"
        assert dim.region_dir == (
            world / "dimensions" / "ftbteamdimensions" / "team" / team_id / "region"
        )


@pytest.mark.asyncio
async def test_walk_depth_bound_rejects_extreme_nesting():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")

        too_deep = world
        for i in range(DIMENSION_MAX_DEPTH_FROM_WORLD_ROOT + 2):
            too_deep = too_deep / f"d{i}"
        _touch(too_deep / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)
        labels = [d.label for d in roots[0].dimensions]
        assert labels == [OVERWORLD_LABEL]


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
        labels = [d.label for d in roots[0].dimensions]
        assert labels == [OVERWORLD_LABEL]


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
