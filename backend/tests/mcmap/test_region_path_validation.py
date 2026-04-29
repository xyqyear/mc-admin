"""Tests for _resolve_region_path safety: rejects traversal, absolute, root."""

import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers.servers.map import _resolve_region_path


@pytest.mark.asyncio
async def test_rejects_absolute_path():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(HTTPException) as exc:
            await _resolve_region_path(Path(d), "/etc/passwd")
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_parent_traversal():
    with tempfile.TemporaryDirectory() as d:
        # ../etc resolves outside the data dir
        with pytest.raises(HTTPException) as exc:
            await _resolve_region_path(Path(d), "../foo")
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_data_root():
    with tempfile.TemporaryDirectory() as d:
        # "." resolves to data_path itself
        with pytest.raises(HTTPException) as exc:
            await _resolve_region_path(Path(d), ".")
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_missing_directory():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(HTTPException) as exc:
            await _resolve_region_path(Path(d), "world/region")
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rejects_file_not_directory():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "world").mkdir()
        (data / "world" / "region").write_text("oops")
        with pytest.raises(HTTPException) as exc:
            await _resolve_region_path(data, "world/region")
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_accepts_valid_relative_dir():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "world" / "region").mkdir(parents=True)
        result = await _resolve_region_path(data, "world/region")
        assert result == (data / "world" / "region").resolve()
