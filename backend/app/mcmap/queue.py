"""Per-(server, region_path) batching render worker with cancellation."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..dynamic_config import config
from ..logger import logger
from . import runner
from .cache import ServerMapCache
from .types import MCMapError

WORKER_IDLE_TIMEOUT_SECONDS = 60.0
BATCH_COLLECT_TIMEOUT_SECONDS = 0.01

Key = Tuple[int, int]


@dataclass
class _PendingRequest:
    x: int
    z: int
    future: asyncio.Future = field(default_factory=lambda: asyncio.Future())
    refs: int = 0
    cancelled: bool = False


class ServerRenderQueue:
    """Single-dimension render queue.

    Coalesces duplicate (x, z) requests via refcount onto a shared Future,
    batches them per render invocation, and terminates the running mcmap
    subprocess if every consumer in the active batch has cancelled.
    """

    def __init__(
        self, server_name: str, region_path: str, cache: ServerMapCache
    ) -> None:
        self._server_name = server_name
        self._region_path = region_path
        self._cache = cache
        self._pending: Dict[Key, _PendingRequest] = {}
        self._queue: asyncio.Queue[_PendingRequest] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running_batch: Optional[Dict[Key, _PendingRequest]] = None
        self._running_proc: Optional[runner.MCMapProcess] = None

    async def request(self, x: int, z: int) -> Path:
        key = (x, z)
        req = self._pending.get(key)
        if req is None:
            loop = asyncio.get_running_loop()
            req = _PendingRequest(x=x, z=z, future=loop.create_future())
            self._pending[key] = req
            self._queue.put_nowait(req)
            self._ensure_worker()
        req.refs += 1
        try:
            # Shield so cancelling one consumer doesn't cancel the underlying
            # future and disturb other consumers coalesced onto the same key.
            return await asyncio.shield(req.future)
        finally:
            req.refs -= 1
            if req.refs == 0 and not req.future.done():
                self._mark_cancelled(key)

    def _ensure_worker(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    def _mark_cancelled(self, key: Key) -> None:
        """Last consumer for key disconnected. Drop it from pending and, if
        the active batch becomes empty, terminate the mcmap subprocess."""
        req = self._pending.pop(key, None)
        if req is not None:
            req.cancelled = True
            if not req.future.done():
                req.future.cancel()
        if self._running_batch is not None and key in self._running_batch:
            del self._running_batch[key]
            if not self._running_batch and self._running_proc is not None:
                proc = self._running_proc
                asyncio.create_task(proc.terminate())

    async def _worker(self) -> None:
        cfg = config.mcmap
        while True:
            try:
                first = await asyncio.wait_for(
                    self._queue.get(), timeout=WORKER_IDLE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                self._worker_task = None
                return

            batch: List[_PendingRequest] = [first]
            try:
                while len(batch) < cfg.batch_size:
                    nxt = await asyncio.wait_for(
                        self._queue.get(), timeout=BATCH_COLLECT_TIMEOUT_SECONDS
                    )
                    batch.append(nxt)
            except asyncio.TimeoutError:
                pass

            live = [
                r for r in batch if not r.cancelled and (r.x, r.z) in self._pending
            ]
            if not live:
                continue

            await self._render_batch(live, cfg.thread_count)

    async def _render_batch(
        self, batch: List[_PendingRequest], threads: int
    ) -> None:
        mcas = [
            self._cache.mca_path(self._region_path, p.x, p.z) for p in batch
        ]
        out_dir = self._cache.tiles_dir(self._region_path)
        self._cache.ensure_dir(out_dir)
        self._running_batch = {(p.x, p.z): p for p in batch}

        try:
            async with runner.render(
                palette=self._cache.palette_json,
                output_dir=out_dir,
                mcas=mcas,
                threads=threads,
                owned_by=self._cache.data_path,
            ) as proc:
                self._running_proc = proc
                async for event in proc:
                    if event.get("type") != "region":
                        continue
                    key: Key = (event["x"], event["z"])
                    if self._running_batch is not None:
                        self._running_batch.pop(key, None)
                    pending = self._pending.pop(key, None)
                    if pending is None or pending.future.done():
                        continue
                    status = event.get("status")
                    if status == "rendered":
                        pending.future.set_result(
                            self._cache.png_path(self._region_path, *key)
                        )
                    elif status == "missing":
                        pending.future.set_exception(
                            FileNotFoundError(f"region ({key[0]}, {key[1]}) missing")
                        )
                    else:
                        pending.future.set_exception(
                            MCMapError(event.get("error", "unknown"))
                        )
        except Exception as e:
            logger.exception(
                "mcmap render batch failed for server=%s region=%s",
                self._server_name,
                self._region_path,
            )
            for p in batch:
                self._pending.pop((p.x, p.z), None)
                if not p.future.done():
                    p.future.set_exception(e)
        finally:
            self._running_proc = None
            self._running_batch = None

        # Defensive: anything in the batch that never received a region event
        # (e.g. subprocess was terminated mid-render).
        for p in batch:
            if (p.x, p.z) in self._pending and not p.future.done():
                self._pending.pop((p.x, p.z), None)
                p.future.set_exception(
                    MCMapError(
                        f"render did not complete for ({p.x}, {p.z})"
                    )
                )
