"""Tests for ServerMapCache ownership helpers (chown + ensure_dir)."""

import tempfile
from pathlib import Path
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


@pytest.mark.asyncio
async def test_chown_calls_os_chown_when_root():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        target = cache.cache_dir
        target.mkdir()
        # Real stat on data_path; only mock chown + geteuid.
        with patch("app.mcmap.cache.os.geteuid", return_value=0), patch(
            "app.mcmap.cache.async_fs.chown", new=AsyncMock()
        ) as ch:
            await cache.chown_to_data_owner(target)
            ch.assert_called_once()
            # uid/gid match the actual data_path owner
            import os as _os
            st = _os.stat(d)
            assert ch.call_args.args == (target, st.st_uid, st.st_gid)


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
async def test_ensure_dir_chowns_only_newly_created_levels():
    """When .mcmap/ already exists, ensure_dir for tiles/<region>/ should chown
    only the levels that didn't exist before — not .mcmap/ itself."""
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        cache.cache_dir.mkdir()  # pre-existing
        target = cache.tiles_dir("world/region")
        with patch.object(
            ServerMapCache, "chown_to_data_owner", new=AsyncMock()
        ) as ch:
            await cache.ensure_dir(target)
            chowned = [call.args[0] for call in ch.call_args_list]
            assert chowned == [
                cache.cache_dir / "tiles",
                cache.cache_dir / "tiles" / "world",
                target,
            ]


@pytest.mark.asyncio
async def test_ensure_dir_chowns_all_levels_when_cache_dir_missing():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        target = cache.tiles_dir("world/region")
        with patch.object(
            ServerMapCache, "chown_to_data_owner", new=AsyncMock()
        ) as ch:
            await cache.ensure_dir(target)
            chowned = [call.args[0] for call in ch.call_args_list]
            assert chowned == [
                cache.cache_dir,
                cache.cache_dir / "tiles",
                cache.cache_dir / "tiles" / "world",
                target,
            ]


@pytest.mark.asyncio
async def test_ensure_dir_does_not_chown_data_path_itself():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        with patch.object(
            ServerMapCache, "chown_to_data_owner", new=AsyncMock()
        ) as ch:
            await cache.ensure_dir(cache.cache_dir)
            chowned = [call.args[0] for call in ch.call_args_list]
            assert cache.data_path not in chowned
            assert chowned == [cache.cache_dir]


@pytest.mark.asyncio
async def test_ensure_dir_idempotent_skips_chown_for_existing_levels():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        target = cache.tiles_dir("world/region")
        target.mkdir(parents=True)  # everything already there
        with patch.object(
            ServerMapCache, "chown_to_data_owner", new=AsyncMock()
        ) as ch:
            await cache.ensure_dir(target)
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
