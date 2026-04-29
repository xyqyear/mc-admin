"""Unit tests for app.world.png_invalidate."""

from pathlib import Path

import pytest

from app.world import png_invalidate


@pytest.fixture
def fake_world(tmp_path: Path) -> Path:
    """Lay out a multi-root world with a few cached tiles."""
    data = tmp_path / "data"
    cache_root = data / ".mcmap" / "tiles"

    for relative in (
        # Default world: Overworld + Nether
        "world/region/r.0.0.png",
        "world/region/r.1.-1.png",
        "world/DIM-1/region/r.0.0.png",
        # Bukkit-style second world root
        "world_creative/region/r.0.0.png",
    ):
        png = cache_root / relative
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"\x89PNG fake")

    # Live MCAs (only structure matters; contents not read by helper)
    for relative in (
        "world/region/r.0.0.mca",
        "world/region/r.1.-1.mca",
        "world/DIM-1/region/r.0.0.mca",
        "world_creative/region/r.0.0.mca",
        "world/entities/r.0.0.mca",  # entities — should NOT have a tile
    ):
        mca = data / relative
        mca.parent.mkdir(parents=True, exist_ok=True)
        mca.write_bytes(b"")

    return data


def _png(data: Path, *parts: str) -> Path:
    return data / ".mcmap" / "tiles" / Path(*parts)


def test_pngs_for_restic_items_picks_up_region_mcas(fake_world: Path):
    """Region MCAs map to their PNG; entities/poi MCAs are skipped."""
    items = [
        str(fake_world / "world/region/r.0.0.mca"),
        str(fake_world / "world_creative/region/r.0.0.mca"),
        str(fake_world / "world/entities/r.0.0.mca"),  # not a region MCA
        str(fake_world / "world/region/level.dat"),  # not an MCA at all
    ]
    pngs = png_invalidate.pngs_for_restic_items(fake_world, items)
    assert pngs == {
        _png(fake_world, "world/region/r.0.0.png"),
        _png(fake_world, "world_creative/region/r.0.0.png"),
    }


def test_pngs_for_restic_items_handles_nested_dimension(fake_world: Path):
    """Nether-style nested dimension paths resolve to the correct cache key."""
    items = [str(fake_world / "world/DIM-1/region/r.0.0.mca")]
    assert png_invalidate.pngs_for_restic_items(fake_world, items) == {
        _png(fake_world, "world/DIM-1/region/r.0.0.png")
    }


def test_pngs_for_restic_items_ignores_unrelated_paths(fake_world: Path):
    """Items outside data_path are silently skipped (no exception)."""
    items = [
        "/some/other/server/world/region/r.0.0.mca",
        str(fake_world / "world/region/r.7.7.mca"),  # under data, valid name
    ]
    assert png_invalidate.pngs_for_restic_items(fake_world, items) == {
        _png(fake_world, "world/region/r.7.7.png")
    }


def test_pngs_for_restic_items_handles_negative_coords(fake_world: Path):
    items = [str(fake_world / "world/region/r.1.-1.mca")]
    assert png_invalidate.pngs_for_restic_items(fake_world, items) == {
        _png(fake_world, "world/region/r.1.-1.png")
    }


def test_pngs_for_regions_simple(fake_world: Path):
    pngs = png_invalidate.pngs_for_regions(
        fake_world, "world/region", [(0, 0), (1, -1)]
    )
    assert pngs == {
        _png(fake_world, "world/region/r.0.0.png"),
        _png(fake_world, "world/region/r.1.-1.png"),
    }


def test_pngs_for_regions_dedupes(fake_world: Path):
    pngs = png_invalidate.pngs_for_regions(
        fake_world, "world/region", [(0, 0), (0, 0)]
    )
    assert len(pngs) == 1


@pytest.mark.asyncio
async def test_delete_pngs_removes_existing_and_skips_missing(fake_world: Path):
    pngs = {
        _png(fake_world, "world/region/r.0.0.png"),
        _png(fake_world, "world_creative/region/r.0.0.png"),
        _png(fake_world, "world/region/r.99.99.png"),  # never existed
    }
    removed = await png_invalidate.delete_pngs(pngs)
    assert removed == 2
    assert not _png(fake_world, "world/region/r.0.0.png").exists()
    assert not _png(fake_world, "world_creative/region/r.0.0.png").exists()
    # untouched tile still there
    assert _png(fake_world, "world/DIM-1/region/r.0.0.png").exists()
