"""Tests for ServerRenderQueue: coalescing, batching, future resolution."""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.mcmap.cache import ServerMapCache
from app.mcmap.queue import ServerRenderQueue


class FakeProc:
    """Fake MCMapProcess that yields pre-scripted events from a list."""

    def __init__(self, events: list, on_terminate=None) -> None:
        self._events = list(events)
        self._terminated = False
        self._on_terminate = on_terminate
        self.returncode = 0

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for ev in self._events:
            await asyncio.sleep(0)  # let other tasks run
            yield ev

    async def terminate(self):
        self._terminated = True
        if self._on_terminate is not None:
            self._on_terminate()


def _patched_runner(events_per_call):
    """Build a context-manager render() that yields scripted events.

    events_per_call: list of event lists, one per render invocation.
    """
    calls = {"i": 0, "mcas": [], "threads": []}

    @asynccontextmanager
    async def fake_render(*, palette, output_dir, mcas, threads, owned_by):
        calls["mcas"].append(list(mcas))
        calls["threads"].append(threads)
        i = calls["i"]
        calls["i"] += 1
        proc = FakeProc(events_per_call[i] if i < len(events_per_call) else [])
        yield proc
        # No teardown work needed; tests assert on outcomes.

    return fake_render, calls


def _mcmap_cfg(batch_size=4, thread_count=2):
    cfg = Mock()
    cfg.batch_size = batch_size
    cfg.thread_count = thread_count
    cfg.request_timeout_seconds = 30
    return cfg


@pytest.fixture
def cache_and_queue():
    with tempfile.TemporaryDirectory() as d:
        data_path = Path(d)
        cache = ServerMapCache(data_path=data_path)
        # Pretend the source MCAs exist (so worker can pass them as -r args)
        for x, z in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            mca = cache.mca_path("world/region", x, z)
            mca.parent.mkdir(parents=True, exist_ok=True)
            mca.write_bytes(b"")
        queue = ServerRenderQueue("srv", "world/region", cache)
        yield cache, queue


async def test_request_resolves_with_png_path(cache_and_queue):
    cache, queue = cache_and_queue
    fake_render, calls = _patched_runner(
        [[{"type": "region", "x": 0, "z": 0, "status": "rendered"}]]
    )
    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg()
        png = await asyncio.wait_for(queue.request(0, 0), timeout=2.0)
        assert png == cache.png_path("world/region", 0, 0)
        # Render was called once with one MCA
        assert len(calls["mcas"]) == 1
        assert len(calls["mcas"][0]) == 1


async def test_duplicate_requests_coalesce_to_single_render(cache_and_queue):
    cache, queue = cache_and_queue
    fake_render, calls = _patched_runner(
        [[{"type": "region", "x": 0, "z": 0, "status": "rendered"}]]
    )
    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg()
        results = await asyncio.wait_for(
            asyncio.gather(queue.request(0, 0), queue.request(0, 0)),
            timeout=2.0,
        )
        assert results[0] == results[1]
        # Render invoked exactly once because both requests share one Future
        assert calls["i"] == 1
        # With the same MCA listed exactly once
        assert len(calls["mcas"][0]) == 1


async def test_batched_requests_in_single_render(cache_and_queue):
    cache, queue = cache_and_queue
    fake_render, calls = _patched_runner(
        [
            [
                {"type": "region", "x": 0, "z": 0, "status": "rendered"},
                {"type": "region", "x": 1, "z": 0, "status": "rendered"},
                {"type": "region", "x": 0, "z": 1, "status": "rendered"},
            ]
        ]
    )
    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg(batch_size=8)
        results = await asyncio.wait_for(
            asyncio.gather(
                queue.request(0, 0),
                queue.request(1, 0),
                queue.request(0, 1),
            ),
            timeout=2.0,
        )
        assert all(isinstance(p, Path) for p in results)
        assert calls["i"] == 1
        assert len(calls["mcas"][0]) == 3


async def test_missing_status_raises_filenotfound(cache_and_queue):
    cache, queue = cache_and_queue
    fake_render, _ = _patched_runner(
        [[{"type": "region", "x": 0, "z": 0, "status": "missing"}]]
    )
    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg()
        with pytest.raises(FileNotFoundError):
            await asyncio.wait_for(queue.request(0, 0), timeout=2.0)


async def test_error_status_raises_render_error(cache_and_queue):
    from app.mcmap.types import MCMapError

    cache, queue = cache_and_queue
    fake_render, _ = _patched_runner(
        [[{"type": "region", "x": 0, "z": 0, "status": "error", "error": "kaboom"}]]
    )
    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg()
        with pytest.raises(MCMapError):
            await asyncio.wait_for(queue.request(0, 0), timeout=2.0)


async def test_missing_event_for_requested_region_raises(cache_and_queue):
    """If mcmap exits without emitting a region event for some mcas, those
    futures must be resolved with MCMapError, not hang forever."""
    from app.mcmap.types import MCMapError

    cache, queue = cache_and_queue
    fake_render, _ = _patched_runner(
        [[{"type": "region", "x": 0, "z": 0, "status": "rendered"}]]
    )
    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg(batch_size=4)
        # Ask for two; only one event will arrive
        results = await asyncio.wait_for(
            asyncio.gather(
                queue.request(0, 0),
                queue.request(1, 0),
                return_exceptions=True,
            ),
            timeout=2.0,
        )
        # First one resolves, second one errors out
        assert isinstance(results[0], Path)
        assert isinstance(results[1], MCMapError)


async def test_worker_reads_mcmap_config_for_each_batch(cache_and_queue):
    cache, queue = cache_and_queue
    fake_render, calls = _patched_runner(
        [
            [{"type": "region", "x": 0, "z": 0, "status": "rendered"}],
            [{"type": "region", "x": 1, "z": 0, "status": "rendered"}],
        ]
    )
    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg(batch_size=1, thread_count=2)
        first = await asyncio.wait_for(queue.request(0, 0), timeout=2.0)

        config_mock.mcmap = _mcmap_cfg(batch_size=1, thread_count=7)
        second = await asyncio.wait_for(queue.request(1, 0), timeout=2.0)

        assert first == cache.png_path("world/region", 0, 0)
        assert second == cache.png_path("world/region", 1, 0)
        assert calls["threads"] == [2, 7]
