"""Per-(server, region_path) batching render worker with cancellation."""

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

import aiofiles.os as aioos

from ..dynamic_config import get_config
from ..errors import log_safe_error
from ..files.resources import path_claims, require_same_claims
from ..operation_admission import get_server_write_admission
from ..operations.context import (
    bind_execution,
    current_execution,
    mark_cache_degraded,
    record_phase,
)
from ..operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from ..operations.journal_types import OperationState
from ..utils import async_fs
from . import runner
from .cache import ServerMapCache
from .events import (
    MCMAP_RENDER_EVENT_ADAPTER,
    MCMapErrorEvent,
    MCMapRenderRegionEvent,
)
from .ownership import PreviewRenderTarget, require_usable_cache
from .types import MCMapError

WORKER_IDLE_TIMEOUT_SECONDS = 60.0
BATCH_COLLECT_TIMEOUT_SECONDS = 0.01

Key = tuple[int, int]


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
        self, server_name: str, region_path: str, cache: ServerMapCache,
        *, preview_target: PreviewRenderTarget | None = None,
    ) -> None:
        self._server_name = preview_target.server_id if preview_target is not None else server_name
        self._region_path = region_path
        self._cache = cache
        self._preview_target = preview_target
        self._pending: dict[Key, _PendingRequest] = {}
        self._queue: asyncio.Queue[_PendingRequest] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._batch_task: asyncio.Task | None = None
        self._running_batch: dict[Key, _PendingRequest] | None = None
        self._running_proc: runner.MCMapProcess | None = None
        self._cleanup_tasks: set[asyncio.Task] = set()
        self._cleanup_errors: list[Exception] = []

    def _track_cleanup(self, task: asyncio.Task) -> None:
        if task in self._cleanup_tasks:
            return
        self._cleanup_tasks.add(task)
        def settled(task: asyncio.Task) -> None:
            self._cleanup_tasks.discard(task)
            if not task.cancelled() and isinstance(error := task.exception(), Exception):
                self._cleanup_errors.append(error)
        task.add_done_callback(settled)

    def shutdown(self) -> None:
        """Cancel the worker, fail outstanding requests, terminate any running
        mcmap subprocess. Idempotent and synchronous — callers don't await it.
        """
        if self._worker_task is not None and not self._worker_task.done():
            self._track_cleanup(self._worker_task)
            self._worker_task.cancel()
        self._worker_task = None
        for req in list(self._pending.values()):
            if not req.future.done():
                req.future.cancel()
        self._pending.clear()
        self._running_batch = None
        if self._running_proc is not None:
            proc = self._running_proc
            self._running_proc = None
            self._track_cleanup(asyncio.create_task(proc.terminate()))

    async def close(self) -> None:
        self.shutdown()
        while self._cleanup_tasks:
            await asyncio.gather(*list(self._cleanup_tasks), return_exceptions=True)
        if self._cleanup_errors:
            errors, self._cleanup_errors = self._cleanup_errors, []
            raise ExceptionGroup("地图渲染写入未能完整停止", errors)

    async def request(self, x: int, z: int) -> Path:
        with get_server_write_admission().write([self._server_name]):
            return await self._request(x, z)

    async def _request(self, x: int, z: int) -> Path:
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
            with bind_execution(None):
                self._worker_task = asyncio.create_task(self._worker())

    def _mark_cancelled(self, key: Key) -> None:
        """Drop ``key`` from pending; terminate the subprocess if the active batch is now empty."""
        req = self._pending.pop(key, None)
        if req is not None:
            req.cancelled = True
            if not req.future.done():
                req.future.cancel()
        if self._running_batch is not None and key in self._running_batch:
            del self._running_batch[key]
            if not self._running_batch and self._batch_task is not None:
                self._batch_task.cancel()

    async def _worker(self) -> None:
        while True:
            try:
                first = await asyncio.wait_for(
                    self._queue.get(), timeout=WORKER_IDLE_TIMEOUT_SECONDS
                )
            except TimeoutError:
                self._worker_task = None
                return

            cfg = get_config().mcmap
            batch: list[_PendingRequest] = [first]
            try:
                while len(batch) < cfg.batch_size:
                    nxt = await asyncio.wait_for(
                        self._queue.get(), timeout=BATCH_COLLECT_TIMEOUT_SECONDS
                    )
                    batch.append(nxt)
            except TimeoutError:
                pass

            live = [
                r for r in batch if not r.cancelled and (r.x, r.z) in self._pending
            ]
            if not live:
                continue

            self._batch_task = asyncio.create_task(self._render_batch(live, cfg.thread_count))
            try:
                await self._batch_task
            except asyncio.CancelledError:
                worker = asyncio.current_task()
                if worker is not None and worker.cancelling():
                    raise
            finally:
                self._batch_task = None

    async def _render_batch(
        self, batch: list[_PendingRequest], threads: int
    ) -> None:
        mcas = [
            self._cache.mca_path(self._region_path, p.x, p.z) for p in batch
        ]
        out_dir = self._cache.tiles_dir(self._region_path)
        self._running_batch = {(p.x, p.z): p for p in batch}
        results: dict[Key, Path | Exception] = {}

        try:
            async def claims_for_output():
                if self._preview_target is not None:
                    for path in [out_dir, *mcas]:
                        await async_fs.resolve_inside(self._preview_target.session_dir, path)
                    palette = await path_claims(self._cache.data_path.parent, [self._cache.palette_json], server_id=self._server_name)
                    return (*palette, ResourceClaim(ResourceKind.MAP_CACHE, self._server_name, f"previews/{self._preview_target.session_id}"))
                cache_claims = await path_claims(self._cache.tiles_dir(""), [out_dir], server_id=self._server_name, kind=ResourceKind.MAP_CACHE)
                files = await path_claims(self._cache.data_path.parent, [out_dir], server_id=self._server_name)
                return (*files, *cache_claims)

            claims = await claims_for_output()
            async with (
                operation_scope("world_preview_render" if self._preview_target is not None else "map_render", [self._server_name], origin="system", claims=claims),
                get_operation_coordinator().acquire(claims),
                settle_before_release(),
                self._preview_target.retained() if self._preview_target is not None else nullcontext(),
            ):
                require_same_claims(claims, await claims_for_output())
                if not self._running_batch:
                    return
                if self._preview_target is not None:
                    await self._preview_target.validate(self._cache.data_path)
                await require_usable_cache(self._server_name)
                await record_phase("rendering_tiles", changed=True)
                await finalize(self._cache.ensure_dir(out_dir))
                try:
                    async with runner.render(
                        palette=self._cache.palette_json,
                        output_dir=out_dir,
                        mcas=mcas,
                        threads=threads,
                        owned_by=self._cache.data_path,
                    ) as proc:
                        self._running_proc = proc
                        async for event in proc.events(MCMAP_RENDER_EVENT_ADAPTER):
                            if isinstance(event, MCMapErrorEvent):
                                raise MCMapError(event.message)
                            if not isinstance(event, MCMapRenderRegionEvent):
                                continue
                            key: Key = (event.x, event.z)
                            pending = next((request for request in batch if (request.x, request.z) == key), None)
                            if pending is None or pending.cancelled:
                                continue
                            if event.status == "rendered":
                                results[key] = self._cache.png_path(self._region_path, *key)
                            elif event.status == "missing":
                                results[key] = FileNotFoundError(f"region ({key[0]}, {key[1]}) missing")
                            else:
                                results[key] = MCMapError(event.error or "unknown")
                    for request in batch:
                        if not request.cancelled and (request.x, request.z) not in results:
                            results[(request.x, request.z)] = MCMapError(f"render did not complete for ({request.x}, {request.z})")
                    incomplete = [request for request in batch if not isinstance(results.get((request.x, request.z)), Path)]
                    await finalize(self._discard_incomplete(incomplete))
                    if any(isinstance(result, MCMapError) for result in results.values()) and (execution := current_execution()) is not None:
                        execution.outcome = OperationState.FAILED
                except BaseException:
                    await finalize(self._discard_incomplete(batch))
                    raise
            for pending in batch:
                key = (pending.x, pending.z)
                if self._pending.get(key) is pending and key in results:
                    self._pending.pop(key)
                    if not pending.future.done():
                        result = results[key]
                        if isinstance(result, Exception):
                            pending.future.set_exception(result)
                        else:
                            pending.future.set_result(result)
        except Exception as e:  # noqa: BLE001 - renderer exception values stay out of application logs
            log_safe_error(e, "mcmap render batch failed")
            for p in batch:
                if self._pending.get((p.x, p.z)) is p:
                    self._pending.pop((p.x, p.z))
                if not p.future.done():
                    p.future.set_exception(e)
        finally:
            self._running_proc = None
            self._running_batch = None

        # Catch entries that never received a region event (e.g. subprocess terminated mid-render).
        for p in batch:
            if self._pending.get((p.x, p.z)) is p and not p.future.done():
                self._pending.pop((p.x, p.z), None)
                p.future.set_exception(
                    MCMapError(
                        f"render did not complete for ({p.x}, {p.z})"
                    )
                )

    async def _discard_incomplete(self, batch: list[_PendingRequest]) -> None:
        execution = current_execution()
        if execution is not None:
            record = await execution.journal.get(execution.operation_id)
            if record is not None and (record.processes or not record.ownership_known):
                await mark_cache_degraded(self._server_name)
                return
        try:
            for request in batch:
                try:
                    path = self._cache.png_path(self._region_path, request.x, request.z)
                    root = self._preview_target.session_dir if self._preview_target is not None else self._cache.data_path
                    await async_fs.resolve_inside(root, path)
                    await aioos.unlink(path)
                except FileNotFoundError:
                    pass
        except Exception:
            await mark_cache_degraded(self._server_name)
            raise
