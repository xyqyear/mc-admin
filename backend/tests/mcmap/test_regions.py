"""Tests for the per-dimension region manifest helper."""

import os
import tempfile
from pathlib import Path

import pytest

from app.routers.servers.map import _list_regions


def _coords_only(triples):
    return [(x, z) for x, z, _ in triples]


@pytest.mark.asyncio
async def test_list_regions_returns_sorted_coords():
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        for x, z in [(0, 0), (1, 0), (-1, -1), (5, 3)]:
            (region / f"r.{x}.{z}.mca").write_bytes(b"x")
        result = await _list_regions(region)
        assert _coords_only(result) == [(-1, -1), (0, 0), (1, 0), (5, 3)]


@pytest.mark.asyncio
async def test_list_regions_includes_mtime():
    """Each entry carries the MCA's mtime so the frontend can append it as a
    cache-busting query param; regeneration changes the URL."""
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        f = region / "r.0.0.mca"
        f.write_bytes(b"x")
        os.utime(f, (1_700_000_000.0, 1_700_000_000.0))
        result = await _list_regions(region)
        assert result == [(0, 0, 1_700_000_000)]


@pytest.mark.asyncio
async def test_list_regions_ignores_non_mca_and_malformed():
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        (region / "r.0.0.mca").write_bytes(b"x")
        (region / "r.foo.bar.mca").write_bytes(b"x")
        (region / "level.dat").write_bytes(b"x")
        (region / "r.1.2.txt").write_bytes(b"x")
        result = await _list_regions(region)
        assert _coords_only(result) == [(0, 0)]


@pytest.mark.asyncio
async def test_list_regions_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        assert await _list_regions(Path(d)) == []


@pytest.mark.asyncio
async def test_list_regions_skips_subdirs_named_like_mca():
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        (region / "r.0.0.mca").write_bytes(b"x")
        # A directory matching the regex must not be counted.
        (region / "r.7.7.mca").mkdir()
        result = await _list_regions(region)
        assert _coords_only(result) == [(0, 0)]


@pytest.mark.asyncio
async def test_list_regions_skips_zero_byte_mcas():
    """0-byte MCAs are unrenderable (mcmap emits UnexpectedEof). Excluding
    them from the manifest lets the frontend short-circuit to a blank tile
    without firing a doomed HTTP request."""
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        (region / "r.0.0.mca").write_bytes(b"x")
        (region / "r.1.1.mca").write_bytes(b"")  # empty: must be skipped
        (region / "r.-2.5.mca").write_bytes(b"x")
        result = await _list_regions(region)
        assert _coords_only(result) == [(-2, 5), (0, 0)]
