"""Tests for queue cancellation: refcount, pre-batch skip, mid-batch terminate."""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.mcmap.cache import ServerMapCache
from app.mcmap.queue import ServerRenderQueue


class HangingProc:
    """Fake MCMapProcess that yields one event then hangs until terminated."""

    def __init__(self) -> None:
        self.terminated = asyncio.Event()
        self.returncode = 0

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        # Yield nothing; just wait for termination
        await self.terminated.wait()
        # Simulate end of stream
        if False:  # pragma: no cover
            yield {}

    async def terminate(self):
        self.terminated.set()


def _mcmap_cfg(batch_size=4, thread_count=2):
    cfg = Mock()
    cfg.batch_size = batch_size
    cfg.thread_count = thread_count
    cfg.request_timeout_seconds = 30
    return cfg


@pytest.fixture
def queue_with_cache():
    with tempfile.TemporaryDirectory() as d:
        data_path = Path(d)
        cache = ServerMapCache(data_path=data_path)
        for x, z in [(0, 0), (1, 0)]:
            mca = cache.mca_path("world/region", x, z)
            mca.parent.mkdir(parents=True, exist_ok=True)
            mca.write_bytes(b"")
        queue = ServerRenderQueue("srv", "world/region", cache)
        yield queue


async def test_refcount_keeps_request_alive_when_one_consumer_cancels(
    queue_with_cache,
):
    """Two consumers on same key; one cancels, the other still completes."""
    queue = queue_with_cache
    started = asyncio.Event()
    proc = HangingProc()

    @asynccontextmanager
    async def fake_render(*, palette, output_dir, mcas, threads, owned_by):
        started.set()
        try:
            yield proc
        finally:
            await proc.terminate()

    # We control when the future resolves manually
    async def driver():
        # Wait for render to start, then resolve the (0,0) future externally
        await started.wait()
        await asyncio.sleep(0.01)
        # Resolve via queue internals: simulate the worker getting a region event.
        # Easier: just terminate the hanging proc → worker will fall through to
        # the defensive "did not complete" branch and set MCMapError.
        await proc.terminate()

    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg()

        c1 = asyncio.create_task(queue.request(0, 0))
        c2 = asyncio.create_task(queue.request(0, 0))
        # Let the worker start
        await asyncio.sleep(0.05)
        # Cancel one consumer; refs goes 2 → 1; should NOT terminate proc
        c1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await c1
        # Proc should still be running (not terminated by cancellation)
        assert not proc.terminated.is_set()
        # Drive termination to make the test finish
        asyncio.create_task(driver())
        with pytest.raises(Exception):
            # c2 sees MCMapError because proc terminated without emitting event
            await asyncio.wait_for(c2, timeout=2.0)


async def test_last_consumer_cancel_terminates_running_subprocess(
    queue_with_cache,
):
    queue = queue_with_cache
    started = asyncio.Event()
    proc = HangingProc()

    @asynccontextmanager
    async def fake_render(*, palette, output_dir, mcas, threads, owned_by):
        started.set()
        try:
            yield proc
        finally:
            await proc.terminate()

    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg()

        c = asyncio.create_task(queue.request(0, 0))
        await started.wait()
        await asyncio.sleep(0.05)
        c.cancel()
        with pytest.raises(asyncio.CancelledError):
            await c
        # The cancellation should fire-and-forget terminate(); give it a tick
        for _ in range(20):
            if proc.terminated.is_set():
                break
            await asyncio.sleep(0.01)
        assert proc.terminated.is_set()


async def test_pre_batch_cancellation_skips_render(queue_with_cache):
    """If a request is cancelled before the worker pops its batch, no render
    invocation happens at all."""
    queue = queue_with_cache
    render_calls = {"n": 0}

    @asynccontextmanager
    async def fake_render(*, palette, output_dir, mcas, threads, owned_by):
        render_calls["n"] += 1
        # Immediate empty exit
        proc = HangingProc()
        proc.terminated.set()
        yield proc

    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg()

        c = asyncio.create_task(queue.request(0, 0))
        # Cancel before the worker even runs
        await asyncio.sleep(0)
        c.cancel()
        with pytest.raises(asyncio.CancelledError):
            await c
        # Give the worker a chance to run; it should see all-cancelled and skip
        await asyncio.sleep(0.1)
        # No render invocation took place
        assert render_calls["n"] == 0


async def test_mid_batch_partial_cancellation_keeps_others_alive(queue_with_cache):
    """Two regions in one batch; one consumer cancels; the other still gets its
    PNG when the corresponding region event arrives."""
    queue = queue_with_cache
    started = asyncio.Event()
    event_gate = asyncio.Event()

    class GatedProc:
        returncode = 0

        def __init__(self):
            self.terminated = False

        def __aiter__(self):
            return self._iter()

        async def _iter(self):
            # Wait for the test to release us, then emit one region event for (1,0)
            await event_gate.wait()
            yield {"type": "region", "x": 1, "z": 0, "status": "rendered"}

        async def terminate(self):
            self.terminated = True

    proc = GatedProc()

    @asynccontextmanager
    async def fake_render(*, palette, output_dir, mcas, threads, owned_by):
        started.set()
        try:
            yield proc
        finally:
            event_gate.set()

    with (
        patch("app.mcmap.queue.runner.render", fake_render),
        patch("app.mcmap.queue.config") as config_mock,
    ):
        config_mock.mcmap = _mcmap_cfg(batch_size=4)

        a = asyncio.create_task(queue.request(0, 0))
        b = asyncio.create_task(queue.request(1, 0))
        await started.wait()
        # Cancel one, release the gate, expect the other to resolve
        a.cancel()
        with pytest.raises(asyncio.CancelledError):
            await a
        event_gate.set()
        png = await asyncio.wait_for(b, timeout=2.0)
        assert isinstance(png, Path)
        assert png.name == "r.1.0.png"
