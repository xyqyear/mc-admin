"""Tests for ServerMapCache path math and freshness checks."""

import os
import tempfile
from pathlib import Path

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


def test_is_fresh_missing_mca():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        assert cache.is_fresh("world/region", 0, 0, 60) == "missing_mca"


def test_is_fresh_missing_png():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        mca.write_bytes(b"x")
        assert cache.is_fresh("world/region", 0, 0, 60) == "missing_png"


def test_is_fresh_zero_byte_mca_treated_as_missing():
    """0-byte MCAs are unrenderable; freshness must report `missing_mca` so
    the tile endpoint short-circuits to 404 instead of queuing a doomed render."""
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        mca.write_bytes(b"")
        assert cache.is_fresh("world/region", 0, 0, 60) == "missing_mca"


def test_is_fresh_fresh_when_within_threshold():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        png = cache.png_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        png.parent.mkdir(parents=True)
        mca.write_bytes(b"x")
        png.write_bytes(b"")
        # PNG older than MCA by 30s; threshold 60s → fresh
        os.utime(png, (1_700_000_000.0, 1_700_000_000.0))
        os.utime(mca, (1_700_000_030.0, 1_700_000_030.0))
        assert cache.is_fresh("world/region", 0, 0, 60) == "fresh"


def test_is_fresh_stale_when_beyond_threshold():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        mca = cache.mca_path("world/region", 0, 0)
        png = cache.png_path("world/region", 0, 0)
        mca.parent.mkdir(parents=True)
        png.parent.mkdir(parents=True)
        mca.write_bytes(b"x")
        png.write_bytes(b"")
        # MCA newer than PNG by 90s; threshold 60s → stale
        os.utime(png, (1_700_000_000.0, 1_700_000_000.0))
        os.utime(mca, (1_700_000_090.0, 1_700_000_090.0))
        assert cache.is_fresh("world/region", 0, 0, 60) == "stale"
