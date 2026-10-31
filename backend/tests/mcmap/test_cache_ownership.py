"""Tests for ServerMapCache ownership helpers (chown + ensure_dir)."""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.mcmap.cache import ServerMapCache


@pytest.mark.asyncio
async def test_ensure_dir_creates_target_and_intermediates():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        target = cache.tiles_dir("world/region")
        assert not target.exists()
        await cache.ensure_dir(target)
        assert target.is_dir()
        assert cache.cache_dir.is_dir()
        assert (cache.cache_dir / "tiles").is_dir()


@pytest.mark.asyncio
async def test_ensure_dir_idempotent_when_already_present():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        target = cache.cache_dir
        target.mkdir()
        await cache.ensure_dir(target)
        assert target.is_dir()


@pytest.mark.asyncio
async def test_ensure_dir_rejects_path_outside_data_path():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
        cache = ServerMapCache(data_path=Path(d))
        with pytest.raises(ValueError):
            await cache.ensure_dir(Path(outside) / "evil")


@pytest.mark.asyncio
async def test_chown_noop_when_not_root():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        target = cache.cache_dir
        target.mkdir()
        with patch("app.mcmap.cache.os.geteuid", return_value=1000), patch(
            "app.mcmap.cache.async_fs.chown", new=AsyncMock()
        ) as ch:
            await cache.chown_to_data_owner(target)
            ch.assert_not_called()


async def test_root_chown_uses_data_owner_instead_of_process_identity(tmp_path):
    cache = ServerMapCache(data_path=tmp_path)
    target = cache.cache_dir
    target.mkdir()
    with (
        patch("app.mcmap.cache.os.geteuid", return_value=0),
        patch("app.mcmap.cache.aioos.stat", new=AsyncMock(
            return_value=SimpleNamespace(st_uid=12345, st_gid=23456),
        )),
        patch("app.mcmap.cache.async_fs.chown", new=AsyncMock()) as chown,
    ):
        await cache.chown_to_data_owner(target)

    chown.assert_awaited_once_with(target, 12345, 23456)


@pytest.mark.asyncio
async def test_chown_noop_when_data_path_missing():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d) / "does_not_exist")
        with patch("app.mcmap.cache.os.geteuid", return_value=0), patch(
            "app.mcmap.cache.async_fs.chown", new=AsyncMock()
        ) as ch:
            await cache.chown_to_data_owner(Path(d))
            ch.assert_not_called()


@pytest.mark.asyncio
async def test_chown_swallows_oserror():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        target = cache.cache_dir
        target.mkdir()
        with patch("app.mcmap.cache.os.geteuid", return_value=0), patch(
            "app.mcmap.cache.async_fs.chown",
            new=AsyncMock(side_effect=PermissionError("nope")),
        ):
            # Should not raise
            await cache.chown_to_data_owner(target)


async def test_cache_creation_preserves_existing_tree_and_inherits_data_owner(tmp_path):
    cache = ServerMapCache(data_path=tmp_path)
    data_before = tmp_path.stat()
    cache.cache_dir.mkdir()
    existing = cache.cache_dir / "retained.png"
    existing.write_bytes(b"previous rendered data")
    existing_before = existing.stat()
    target = cache.tiles_dir("world/region")

    await cache.ensure_dir(target)
    await cache.ensure_dir(target)

    assert target.is_dir()
    for directory in (cache.cache_dir / "tiles", cache.cache_dir / "tiles/world", target):
        owner = directory.stat()
        assert (owner.st_uid, owner.st_gid) == (data_before.st_uid, data_before.st_gid)
    assert existing.read_bytes() == b"previous rendered data"
    assert existing.stat().st_ino == existing_before.st_ino
    assert existing.stat().st_mtime_ns == existing_before.st_mtime_ns
    assert (tmp_path.stat().st_uid, tmp_path.stat().st_gid) == (data_before.st_uid, data_before.st_gid)
