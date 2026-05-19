import tempfile
from pathlib import Path

import pytest

from app.world.layout import (
    END_LABEL,
    NETHER_LABEL,
    OVERWORLD_LABEL,
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

        # Non-dim siblings under the world root must not crash the walker.
        _touch(world / "playerdata" / "uuid.dat")
        _touch(world / "ftbchunks" / "data.snbt")

        roots = await discover_world_roots(data_path)

        assert len(roots) == 1
        labels = {d.label for d in roots[0].dimensions}
        assert labels == {
            OVERWORLD_LABEL,
            NETHER_LABEL,
            "dimensions/allthemodium/mining",
            "dimensions/allthemodium/the_beyond",
            "dimensions/ad_astra/moon",
        }

        by_label = {d.label: d for d in roots[0].dimensions}
        assert by_label["dimensions/allthemodium/mining"].region_dir == (
            world / "dimensions" / "allthemodium" / "mining" / "region"
        )


@pytest.mark.asyncio
async def test_walk_depth_bound_rejects_extreme_nesting():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")

        # ``visit`` checks the dim BEFORE the depth guard, so a dim at exactly
        # MAX_DEPTH is still recorded. Push the dim one level past that.
        too_deep = world / "a" / "b" / "c" / "d" / "e" / "f" / "g"
        _touch(too_deep / "region" / "r.0.0.mca")

        roots = await discover_world_roots(data_path)
        labels = [d.label for d in roots[0].dimensions]
        assert labels == [OVERWORLD_LABEL]


@pytest.mark.asyncio
async def test_skips_mcmap_dir():
    with tempfile.TemporaryDirectory(prefix="layout_test_") as tmp:
        data_path = Path(tmp)
        _write_properties(data_path, "world")
        world = data_path / "world"
        _touch(world / "level.dat")
        _touch(world / "region" / "r.0.0.mca")
        # .mcmap directory at the data root should not be discovered.
        _touch(data_path / ".mcmap" / "palette.hash")
        # .mcmap directory inside the world should not be considered a dimension.
        _touch(world / ".mcmap" / "tiles" / "0_0.png")

        roots = await discover_world_roots(data_path)
        assert len(roots) == 1
        assert roots[0].name == "world"
        labels = [d.label for d in roots[0].dimensions]
        assert labels == [OVERWORLD_LABEL]
