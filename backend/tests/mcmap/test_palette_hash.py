import tempfile
from pathlib import Path

import pytest

from app.mcmap.cache import ServerMapCache
from app.mcmap.palette import (
    compute_palette_hash,
    discover_level_dat,
    discover_mods_dir,
    palette_is_current,
    write_palette_hash,
)


@pytest.mark.asyncio
async def test_hash_stable_under_same_inputs():
    with tempfile.TemporaryDirectory() as d:
        mods = Path(d) / "mods"
        mods.mkdir()
        (mods / "create.jar").write_bytes(b"")
        (mods / "jei.jar").write_bytes(b"")
        h1 = await compute_palette_hash("1.20.1", mods)
        h2 = await compute_palette_hash("1.20.1", mods)
        assert h1 == h2


@pytest.mark.asyncio
async def test_hash_invariant_under_mod_iteration_order():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        mods1 = Path(d1) / "mods"
        mods1.mkdir()
        (mods1 / "a.jar").write_bytes(b"")
        (mods1 / "b.jar").write_bytes(b"")
        mods2 = Path(d2) / "mods"
        mods2.mkdir()
        # Create in opposite order
        (mods2 / "b.jar").write_bytes(b"")
        (mods2 / "a.jar").write_bytes(b"")
        assert await compute_palette_hash("1.20.1", mods1) == await compute_palette_hash(
            "1.20.1", mods2
        )


@pytest.mark.asyncio
async def test_hash_changes_when_version_changes():
    with tempfile.TemporaryDirectory() as d:
        mods = Path(d) / "mods"
        mods.mkdir()
        (mods / "create.jar").write_bytes(b"")
        h1 = await compute_palette_hash("1.20.1", mods)
        h2 = await compute_palette_hash("1.21.4", mods)
        assert h1 != h2


@pytest.mark.asyncio
async def test_hash_changes_when_mod_added():
    with tempfile.TemporaryDirectory() as d:
        mods = Path(d) / "mods"
        mods.mkdir()
        (mods / "create.jar").write_bytes(b"")
        h1 = await compute_palette_hash("1.20.1", mods)
        (mods / "jei.jar").write_bytes(b"")
        h2 = await compute_palette_hash("1.20.1", mods)
        assert h1 != h2


@pytest.mark.asyncio
async def test_hash_ignores_non_jar_files():
    with tempfile.TemporaryDirectory() as d:
        mods = Path(d) / "mods"
        mods.mkdir()
        (mods / "create.jar").write_bytes(b"")
        h1 = await compute_palette_hash("1.20.1", mods)
        (mods / "readme.txt").write_text("hi")
        h2 = await compute_palette_hash("1.20.1", mods)
        assert h1 == h2


@pytest.mark.asyncio
async def test_hash_with_no_mods_dir():
    h_none = await compute_palette_hash("1.20.1", None)
    with tempfile.TemporaryDirectory() as d:
        mods = Path(d) / "mods_does_not_exist"
        h_missing = await compute_palette_hash("1.20.1", mods)
    assert h_none == h_missing


@pytest.mark.asyncio
async def test_palette_is_current_lifecycle():
    with tempfile.TemporaryDirectory() as d:
        cache = ServerMapCache(data_path=Path(d))
        cache.cache_dir.mkdir()
        # No palette files: not current
        assert await palette_is_current(cache, "1.20.1", None) is False
        # Write palette + matching hash: current
        cache.palette_json.write_text("{}")
        await write_palette_hash(cache, "1.20.1", None)
        assert await palette_is_current(cache, "1.20.1", None) is True
        # Different version: not current
        assert await palette_is_current(cache, "1.21.4", None) is False


@pytest.mark.asyncio
async def test_discover_mods_dir():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        # No mods dir
        assert await discover_mods_dir(data) is None
        # Empty mods dir
        (data / "mods").mkdir()
        assert await discover_mods_dir(data) is None
        # Non-jar contents
        (data / "mods" / "readme.txt").write_text("")
        assert await discover_mods_dir(data) is None
        # With at least one jar
        (data / "mods" / "x.jar").write_bytes(b"")
        assert await discover_mods_dir(data) == data / "mods"


@pytest.mark.asyncio
async def test_discover_level_dat_default_world():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        # No world dir at all
        assert await discover_level_dat(data) is None
        # world/ exists but no level.dat
        (data / "world").mkdir()
        assert await discover_level_dat(data) is None
        # default location populated
        (data / "world" / "level.dat").write_bytes(b"stub")
        assert await discover_level_dat(data) == data / "world" / "level.dat"


@pytest.mark.asyncio
async def test_discover_level_dat_honors_level_name():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "server.properties").write_text("level-name=custom_world\n")
        (data / "custom_world").mkdir()
        (data / "custom_world" / "level.dat").write_bytes(b"stub")
        assert (
            await discover_level_dat(data)
            == data / "custom_world" / "level.dat"
        )


@pytest.mark.asyncio
async def test_discover_level_dat_missing_level_name_falls_back():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        # level-name points at a dir that doesn't exist
        (data / "server.properties").write_text("level-name=missing\n")
        assert await discover_level_dat(data) is None
