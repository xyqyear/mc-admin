"""Snapshot preview session lifecycle.

Sessions stage snapshot MCAs (and chunk-merged copies for CHUNKS scope) to
``/tmp`` and render them to PNGs. At most one active session per server.
Heartbeat-driven TTL with a janitor loop reaping stale sessions and orphans.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles.os as aioos
from fastapi import HTTPException

from ..dynamic_config import get_config
from ..errors import PublicOperationError
from ..utils import async_fs
from ..world.artifacts import (
    protected_artifacts,
    reap_restore_stages,
    retain_artifact,
    valid_artifact_id,
)
from .preview_models import PreviewBinding, PreviewResult
from .repository_use import RepositoryUse

if TYPE_CHECKING:
    from ..mcmap.queue import ServerRenderQueue

logger = logging.getLogger(__name__)


class PreviewDiskGuardError(PublicOperationError):
    """Raised when a preview cannot be created due to insufficient disk space."""

    def __init__(self, free: int, required: int) -> None:
        super().__init__(
            f"预览临时空间不足：可用 {free} 字节，需要 {required} 字节"
        )
        self.free = free
        self.required = required


class PreviewSessionNotFoundError(HTTPException):
    def __init__(self, session_id: str) -> None:
        super().__init__(status_code=404, detail="预览不存在或已过期，请重新准备")


@dataclass
class _Session:
    session_id: str
    server_id: str | None
    base_dir: Path
    last_seen: datetime
    affected_regions: int = 0
    render_queue: ServerRenderQueue | None = None
    affected_keys: set[tuple[int, int]] | None = None
    references: int = 0
    closing: bool = False
    server_generation: int | None = None
    snapshot_reference: AbstractContextManager[None] | None = None
    owner_keys: tuple[str | None, ...] = ()
    binding: PreviewBinding | None = None
    result: PreviewResult | None = None
    idle: asyncio.Event = field(default_factory=asyncio.Event)
    destroy_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PreviewSessionManager:
    """Manage ``/tmp`` preview session dirs, heartbeats, and the janitor loop."""

    def __init__(
        self, base_dir: Path, repository_use: RepositoryUse | None = None
    ) -> None:
        self.base_dir = base_dir
        self._repository_use = repository_use or RepositoryUse()
        self._sessions: dict[str, _Session] = {}
        self._server_to_session: dict[str | None, str] = {}
        self._janitor_task: asyncio.Task | None = None
        self._creation_lock = asyncio.Lock()
        self._now: Callable[[], datetime] = _utcnow
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def create_session(
        self,
        server_id: str | None,
        *,
        affected_regions: int = 0,
        server_generation: int | None = None,
        source_snapshot_id: str | None = None,
        server_ids: tuple[str, ...] = (),
    ) -> Path:
        """Tear down any prior session for ``server_id`` and create a fresh dir.

        Raises ``PreviewDiskGuardError`` if free space is below the heuristic.
        """
        region_bytes = get_config().snapshots.world_restore.preview_avg_region_bytes
        required = max(affected_regions, 1) * region_bytes * 2
        free = await self.disk_free_bytes()
        if free < required:
            raise PreviewDiskGuardError(free=free, required=required)

        from ..operations.finalization import finalize
        from ..world.artifacts import release_artifact

        async with self._creation_lock:
            owners = tuple(dict.fromkeys((server_id, *server_ids)))
            prior_sessions = {
                self._server_to_session[key]
                for key in owners
                if key in self._server_to_session
            }
            for prior in prior_sessions:
                await finalize(self.end(prior))
            if len(self._sessions) >= 256:
                raise HTTPException(
                    status_code=423, detail="活动预览过多，请等待清理完成"
                )

            session_id = secrets.token_hex(16)
            session_dir = self.base_dir / session_id
            self._sessions[session_id] = _Session(
                session_id=session_id,
                server_id=server_id,
                base_dir=session_dir,
                last_seen=self._now(),
                affected_regions=affected_regions,
                server_generation=server_generation,
                owner_keys=owners,
            )
            for owner in owners:
                self._server_to_session[owner] = session_id
            try:
                if source_snapshot_id is not None:
                    reference = self._repository_use.retain([source_snapshot_id])
                    reference.__enter__()
                    self._sessions[session_id].snapshot_reference = reference
                await retain_artifact("world_preview", session_id)
                await finalize(aioos.makedirs(session_dir, exist_ok=False))
            except BaseException:

                async def cleanup() -> None:
                    await release_artifact("world_preview", session_id)
                    await self.end(session_id)

                await finalize(cleanup())
                raise
            return session_dir

    def heartbeat(self, session_id: str) -> None:
        sess = self._sessions.get(session_id)
        if sess is None or sess.closing or sess.last_seen < self._now() - self._ttl():
            raise PreviewSessionNotFoundError(session_id)
        sess.last_seen = self._now()

    async def end(self, session_id: str) -> None:
        """Idempotent teardown."""
        sess = self._sessions.get(session_id)
        if sess is None:
            return
        sess.closing = True
        for owner in sess.owner_keys:
            if self._server_to_session.get(owner) == session_id:
                self._server_to_session.pop(owner, None)
        if sess.references:
            return
        from ..operations.finalization import finalize

        await finalize(self._destroy(sess))

    async def end_and_wait(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        await self.end(session_id)
        if session is None:
            return
        while session.references:
            await session.idle.wait()
        await self.end(session_id)
        if session_id in self._sessions:
            raise HTTPException(
                status_code=423,
                detail="预览写入状态尚未确认，临时数据已保留，请核对操作历史",
            )

    async def _destroy(self, sess: _Session) -> None:
        async with sess.destroy_lock:
            if sess.session_id not in self._sessions:
                return
            if sess.render_queue is not None:
                await sess.render_queue.close()
            if sess.session_id in await protected_artifacts("world_preview"):
                return
            try:
                await async_fs.rmtree(sess.base_dir, ignore_errors=False)
            except FileNotFoundError:
                pass
            self._sessions.pop(sess.session_id, None)
            if sess.snapshot_reference is not None:
                sess.snapshot_reference.__exit__(None, None, None)
                sess.snapshot_reference = None

    @asynccontextmanager
    async def use(self, session_id: str) -> AsyncGenerator[_Session]:
        self.heartbeat(session_id)
        session = self._sessions[session_id]
        session.references += 1
        session.idle.clear()
        try:
            yield session
        finally:
            session.references -= 1
            if not session.references:
                session.idle.set()
            if session.closing and not session.references:
                from ..operations.finalization import finalize

                await finalize(self._destroy(session))

    def get_active_for_server(self, server_id: str | None) -> str | None:
        return self._server_to_session.get(server_id)

    def get_session(self, session_id: str) -> _Session | None:
        session = self._sessions.get(session_id)
        return session if session is not None and not session.closing else None

    def get_session_dir(self, session_id: str) -> Path | None:
        sess = self.get_session(session_id)
        return sess.base_dir if sess else None

    async def get_tile_path(self, session_id: str, rx: int, rz: int) -> Path | None:
        sess = self._sessions.get(session_id)
        if sess is None:
            return None
        candidate = sess.base_dir / "tiles" / f"r.{rx}.{rz}.png"
        return candidate if await aioos.path.exists(candidate) else None

    def attach_render_queue(
        self,
        session_id: str,
        *,
        queue: ServerRenderQueue,
        affected_keys: set[tuple[int, int]],
    ) -> None:
        """Bind ``queue`` and the staged (rx, rz) set; callers must 404 keys outside it."""
        sess = self._sessions.get(session_id)
        if sess is None:
            raise PreviewSessionNotFoundError(session_id)
        # Re-staging on the same session: shut down the prior worker first.
        if sess.render_queue is not None:
            sess.render_queue.shutdown()
        sess.render_queue = queue
        sess.affected_keys = set(affected_keys)

    async def disk_free_bytes(self) -> int:
        usage = await async_fs.disk_usage(self.base_dir)
        return usage.free

    def _ttl(self) -> timedelta:
        return timedelta(
            seconds=get_config().snapshots.world_restore.preview_session_ttl_seconds
        )

    async def reap_stale(self) -> list[str]:
        """End sessions whose ``last_seen`` is older than the TTL; return their ids."""
        cutoff = self._now() - self._ttl()
        stale = [sid for sid, s in self._sessions.items() if s.last_seen < cutoff]
        for sid in stale:
            await self.end(sid)
        return stale

    async def reap_orphan_dirs(self) -> list[Path]:
        """Delete child dirs of ``base_dir`` not tracked in ``_sessions``; return their paths."""
        if not await aioos.path.exists(self.base_dir):
            return []
        deleted: list[Path] = []
        for child in await async_fs.iterdir(self.base_dir):
            if (
                not valid_artifact_id(child.name)
                or not await aioos.path.isdir(child)
                or await aioos.path.islink(child)
            ):
                continue
            async with self._creation_lock:
                protected = await protected_artifacts("world_preview")
                if child.name in self._sessions or child.name in protected:
                    continue
                await async_fs.rmtree(child, ignore_errors=True)
                deleted.append(child)
        return deleted

    async def janitor_loop(self) -> None:
        """Reap stale sessions and orphan dirs forever; tolerant of transient errors."""
        while True:
            try:
                interval = get_config().snapshots.world_restore.preview_janitor_interval_seconds
                await asyncio.sleep(interval)
                await self.reap_stale()
                await self.reap_orphan_dirs()
                await reap_restore_stages()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("preview janitor: unexpected error; continuing")

    def start_janitor(self) -> asyncio.Task:
        if self._janitor_task is not None and not self._janitor_task.done():
            return self._janitor_task
        self._janitor_task = asyncio.create_task(self.janitor_loop())
        return self._janitor_task

    async def stop_janitor(self) -> None:
        task = self._janitor_task
        self._janitor_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Preview janitor failed during shutdown")

    async def close(self, *, preserve_artifacts: bool = False) -> None:
        await self.stop_janitor()
        errors = []
        for session_id in list(self._sessions):
            try:
                if preserve_artifacts:
                    queue = self._sessions[session_id].render_queue
                    if queue is not None:
                        await queue.close()
                else:
                    await self.end(session_id)
            except Exception as error:  # noqa: BLE001
                errors.append(error)
        if errors:
            raise ExceptionGroup("部分预览会话未能完整关闭", errors)
