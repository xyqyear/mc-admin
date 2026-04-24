"""Tests for the per-dimension region manifest helper."""

import tempfile
from pathlib import Path

from app.routers.servers.map import _list_regions


def test_list_regions_returns_sorted_coords():
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        for x, z in [(0, 0), (1, 0), (-1, -1), (5, 3)]:
            (region / f"r.{x}.{z}.mca").write_bytes(b"")
        result = _list_regions(region)
        assert result == [(-1, -1), (0, 0), (1, 0), (5, 3)]


def test_list_regions_ignores_non_mca_and_malformed():
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        (region / "r.0.0.mca").write_bytes(b"")
        (region / "r.foo.bar.mca").write_bytes(b"")
        (region / "level.dat").write_bytes(b"")
        (region / "r.1.2.txt").write_bytes(b"")
        result = _list_regions(region)
        assert result == [(0, 0)]


def test_list_regions_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        assert _list_regions(Path(d)) == []


def test_list_regions_skips_subdirs_named_like_mca():
    with tempfile.TemporaryDirectory() as d:
        region = Path(d)
        (region / "r.0.0.mca").write_bytes(b"")
        # A directory matching the regex must not be counted.
        (region / "r.7.7.mca").mkdir()
        result = _list_regions(region)
        assert result == [(0, 0)]
