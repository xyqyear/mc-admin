import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.world import layout_cache
from app.world.layout import WorldRoot


@pytest.mark.asyncio
async def test_layout_cache_coalesces_concurrent_discovery(monkeypatch):
    await layout_cache.clear_world_layout_cache()
    calls = 0
    gate = asyncio.Event()
    roots = [WorldRoot(name="world", path=Path("/srv/world"), dimensions=[])]

    async def fake_discover(data_path: Path):
        nonlocal calls
        calls += 1
        await gate.wait()
        return roots

    monkeypatch.setattr(layout_cache, "discover_world_roots", fake_discover)
    first = asyncio.create_task(layout_cache.get_cached_world_roots(Path("/srv")))
    second = asyncio.create_task(layout_cache.get_cached_world_roots(Path("/srv")))

    await asyncio.sleep(0)
    gate.set()

    assert await first is roots
    assert await second is roots
    assert calls == 1

    assert await layout_cache.get_cached_world_roots(Path("/srv")) is roots
    assert calls == 1
    await layout_cache.clear_world_layout_cache()


@pytest.mark.asyncio
async def test_layout_cache_uses_dynamic_ttl(monkeypatch):
    await layout_cache.clear_world_layout_cache()
    calls = 0
    roots = [WorldRoot(name="world", path=Path("/srv/world"), dimensions=[])]

    async def fake_discover(data_path: Path):
        nonlocal calls
        calls += 1
        return roots

    monkeypatch.setattr(layout_cache, "discover_world_roots", fake_discover)
    monkeypatch.setattr(
        layout_cache,
        "config",
        SimpleNamespace(world=SimpleNamespace(layout_cache_ttl_seconds=0.0)),
    )

    assert await layout_cache.get_cached_world_roots(Path("/srv")) is roots
    assert await layout_cache.get_cached_world_roots(Path("/srv")) is roots
    assert calls == 2
    await layout_cache.clear_world_layout_cache()
