"""Tests for map dimension projection from world layout discovery."""

import tempfile
from pathlib import Path

import pytest

from app.routers.servers.map import _discover_dimensions
from app.world.dimension_labels import label_for_dimension_dir


def test_label_for_overworld():
    world = Path("/data/world")
    assert label_for_dimension_dir(world, world) == "Overworld"


def test_label_for_nether():
    world = Path("/data/world")
    assert label_for_dimension_dir(world, world / "DIM-1") == "Nether"


def test_label_for_end():
    world = Path("/data/world")
    assert label_for_dimension_dir(world, world / "DIM1") == "End"


def test_label_for_vanilla_dimension_directory_layout():
    world = Path("/data/world")
    assert (
        label_for_dimension_dir(world, world / "dimensions" / "minecraft" / "overworld")
        == "Overworld"
    )
    assert (
        label_for_dimension_dir(
            world, world / "dimensions" / "minecraft" / "the_nether"
        )
        == "Nether"
    )
    assert (
        label_for_dimension_dir(world, world / "dimensions" / "minecraft" / "the_end")
        == "End"
    )


def test_label_fallback_to_path():
    world = Path("/data/world")
    assert label_for_dimension_dir(world, world / "DIM88") == "DIM88"
    assert (
        label_for_dimension_dir(world, world / "dimensions" / "example" / "custom")
        == "example/custom"
    )


@pytest.mark.asyncio
async def test_discover_skips_mcmap_cache_dir():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        # Real region
        (data / "world").mkdir(parents=True)
        (data / "world" / "level.dat").write_bytes(b"")
        ow = data / "world" / "region"
        ow.mkdir(parents=True)
        (ow / "r.0.0.mca").write_bytes(b"")
        # .mcmap should be skipped even if it contains MCA files
        cache_region = data / ".mcmap" / "tiles" / "world" / "region"
        cache_region.mkdir(parents=True)
        (cache_region / "r.0.0.mca").write_bytes(b"")  # would falsely match
        results = await _discover_dimensions(data)
        paths = {r.region_path for r in results}
        assert "world/region" in paths
        assert not any(p.startswith(".mcmap") for p in paths)


@pytest.mark.asyncio
async def test_discover_finds_multiple_dimensions():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        for root in ["world", "world_nether", "world_the_end"]:
            (data / root).mkdir(parents=True, exist_ok=True)
            (data / root / "level.dat").write_bytes(b"")
        for sub, n in [
            ("world/region", 3),
            ("world_nether/DIM-1/region", 1),
            ("world_the_end/DIM1/region", 2),
            ("world/dimensions/minecraft/the_nether/region", 4),
        ]:
            (data / sub).mkdir(parents=True)
            for i in range(n):
                (data / sub / f"r.{i}.0.mca").write_bytes(b"")
        results = await _discover_dimensions(data)
        by_path = {r.region_path: r for r in results}
        assert by_path["world/region"].mca_count == 3
        assert by_path["world/region"].label == "Overworld"
        assert by_path["world_nether/DIM-1/region"].mca_count == 1
        assert by_path["world_nether/DIM-1/region"].label == "Nether"
        assert by_path["world_the_end/DIM1/region"].mca_count == 2
        assert by_path["world_the_end/DIM1/region"].label == "End"
        assert by_path["world/dimensions/minecraft/the_nether/region"].mca_count == 4
        assert by_path["world/dimensions/minecraft/the_nether/region"].label == "Nether"


@pytest.mark.asyncio
async def test_discover_ignores_non_mca_files_and_negative_coords():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "world").mkdir(parents=True)
        (data / "world" / "level.dat").write_bytes(b"")
        region = data / "world" / "region"
        region.mkdir(parents=True)
        (region / "r.0.0.mca").write_bytes(b"")
        (region / "r.-1.-1.mca").write_bytes(b"")  # negative coords valid
        (region / "level.dat").write_bytes(b"")
        (region / "r.foo.bar.mca").write_bytes(b"")  # malformed name
        results = await _discover_dimensions(data)
        assert len(results) == 1
        assert results[0].mca_count == 2


@pytest.mark.asyncio
async def test_discover_empty_data_dir():
    with tempfile.TemporaryDirectory() as d:
        assert await _discover_dimensions(Path(d)) == []


@pytest.mark.asyncio
async def test_discover_skips_entities_and_poi_siblings():
    """`entities/` and `poi/` are siblings of `region/` inside a dimension and
    also contain r.X.Z.mca files (entity / POI data), but they are not
    renderable map terrain and must not appear as dimensions."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "world").mkdir(parents=True)
        (data / "world" / "level.dat").write_bytes(b"")
        for sub in ["world/region", "world/entities", "world/poi"]:
            (data / sub).mkdir(parents=True)
            (data / sub / "r.0.0.mca").write_bytes(b"")
        results = await _discover_dimensions(data)
        paths = {r.region_path for r in results}
        assert paths == {"world/region"}


@pytest.mark.asyncio
async def test_discover_skips_entities_and_poi_in_other_dimensions():
    """Same exclusion applies to nether/end dimension folders."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        for root in ["world", "world_nether", "world_the_end"]:
            (data / root).mkdir(parents=True, exist_ok=True)
            (data / root / "level.dat").write_bytes(b"")
        for sub in [
            "world/region",
            "world/entities",
            "world/poi",
            "world_nether/DIM-1/region",
            "world_nether/DIM-1/entities",
            "world_nether/DIM-1/poi",
            "world_the_end/DIM1/region",
            "world_the_end/DIM1/entities",
            "world_the_end/DIM1/poi",
        ]:
            (data / sub).mkdir(parents=True)
            (data / sub / "r.0.0.mca").write_bytes(b"")
        results = await _discover_dimensions(data)
        paths = {r.region_path for r in results}
        assert paths == {
            "world/region",
            "world_nether/DIM-1/region",
            "world_the_end/DIM1/region",
        }
