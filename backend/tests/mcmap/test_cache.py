"""Tests for ServerMapCache path math and freshness checks."""

import os
import tempfile
from pathlib import Path

import pytest

from app.mcmap.cache import ServerMapCache


def test_cache_paths():
    cache = ServerMapCache(data_path=Path("/srv/mc/world/data"))
    assert cache.cache_dir == Path("/srv/mc/world/data/.mcmap")
    assert cache.client_jar == Path("/srv/mc/world/data/.mcmap/client.jar")
    assert cache.palette_json == Path("/srv/mc/world/data/.mcmap/palette.json")
    assert cache.palette_hash_file == Path("/srv/mc/world/data/.mcmap/palette.hash")
    assert cache.tiles_dir("world/region") == Path(
        "/srv/mc/world/data/.mcmap/tiles/world/region"
    )
    assert cache.mca_path("world/region", 0, 0) == Path(
        "/srv/mc/world/data/world/region/r.0.0.mca"
    )
    assert cache.mca_path("world/region", -3, 12) == Path(
        "/srv/mc/world/data/world/region/r.-3.12.mca"
    )
    assert cache.png_path("world/region", 1, -2) == Path(
        "/srv/mc/world/data/.mcmap/tiles/world/region/r.1.-2.png"
    )


@pytest.mark.asyncio
async def test_is_fresh_missing_mca():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        assert await cache.is_fresh("world/region", 0, 0) == "missing_mca"


@pytest.mark.asyncio
async def test_is_fresh_missing_png():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        mca.write_bytes(b"x")
        assert await cache.is_fresh("world/region", 0, 0) == "missing_png"


@pytest.mark.asyncio
async def test_is_fresh_zero_byte_mca_treated_as_missing():
    """0-byte MCAs are unrenderable; freshness must report `missing_mca` so
    the tile endpoint short-circuits to 404 instead of queuing a doomed render."""
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        mca.write_bytes(b"")
        assert await cache.is_fresh("world/region", 0, 0) == "missing_mca"


@pytest.mark.asyncio
async def test_is_fresh_fresh_when_mtimes_match():
    """mcmap renders with `--preserve-mtime`, so a PNG that matches its
    source MCA's mtime exactly is current."""
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        png = cache.png_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        png.parent.mkdir(parents=True)
        mca.write_bytes(b"x")
        png.write_bytes(b"")
        os.utime(png, (1_700_000_000.0, 1_700_000_000.0))
        os.utime(mca, (1_700_000_000.0, 1_700_000_000.0))
        assert await cache.is_fresh("world/region", 0, 0) == "fresh"


@pytest.mark.asyncio
async def test_is_fresh_stale_when_mca_newer():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        png = cache.png_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        png.parent.mkdir(parents=True)
        mca.write_bytes(b"x")
        png.write_bytes(b"")
        os.utime(png, (1_700_000_000.0, 1_700_000_000.0))
        os.utime(mca, (1_700_000_001.0, 1_700_000_001.0))
        assert await cache.is_fresh("world/region", 0, 0) == "stale"


@pytest.mark.asyncio
async def test_is_fresh_stale_when_png_newer():
    """Any divergence — even a PNG newer than the MCA — forces a re-render."""
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        png = cache.png_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        png.parent.mkdir(parents=True)
        mca.write_bytes(b"x")
        png.write_bytes(b"")
        os.utime(mca, (1_700_000_000.0, 1_700_000_000.0))
        os.utime(png, (1_700_000_001.0, 1_700_000_001.0))
        assert await cache.is_fresh("world/region", 0, 0) == "stale"
