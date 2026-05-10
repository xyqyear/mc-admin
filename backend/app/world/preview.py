"""Per-server world-restore preview session lifecycle.

Sessions stage snapshot MCAs (and chunk-merged copies for CHUNKS scope) to
``/tmp`` and render them to PNGs. At most one active session per server.
Heartbeat-driven TTL with a janitor loop reaping stale sessions and orphans.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

import aiofiles.os as aioos

from ..utils import async_fs

if TYPE_CHECKING:
    from ..mcmap.queue import ServerRenderQueue

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 600
DEFAULT_JANITOR_INTERVAL_SECONDS = 60
AVG_REGION_BYTES = 8 * 1024 * 1024


class PreviewDiskGuardError(RuntimeError):
    """Raised when a preview cannot be created due to insufficient disk space."""

    def __init__(self, free: int, required: int) -> None:
        super().__init__(
            f"insufficient disk for preview: {free} bytes free, {required} bytes required"
        )
        self.free = free
        self.required = required


class PreviewSessionNotFoundError(KeyError):
    """Raised when a session_id is not registered."""


@dataclass
class _Session:
    session_id: str
    server_id: str
    base_dir: Path
    last_seen: datetime
    affected_regions: int = 0
    render_queue: Optional["ServerRenderQueue"] = None
    affected_keys: Optional[set[tuple[int, int]]] = None


@dataclass
class PreviewMapCache:
    """``ServerMapCache``-shaped resolver for preview rendering.

    Implements the surface ``ServerRenderQueue`` reaches into, rooted at a
    session's staged MCAs and a session-local tiles dir. ``data_path``
    points at the live world's data dir so mcmap's ``--chown`` targets the
    data-dir owner; ``palette_json`` reuses the live world's palette.
    """

    palette_json: Path
    data_path: Path
    staged_region_dir: Path
    tiles_root: Path

    def mca_path(self, _region_path: str, x: int, z: int) -> Path:
        return self.staged_region_dir / f"r.{x}.{z}.mca"

    def tiles_dir(self, _region_path: str) -> Path:
        return self.tiles_root

    def png_path(self, _region_path: str, x: int, z: int) -> Path:
        return self.tiles_root / f"r.{x}.{z}.png"

    async def ensure_dir(self, target: Path) -> None:
        await aioos.makedirs(target, exist_ok=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PreviewSessionManager:
    """Manage ``/tmp`` preview session dirs, heartbeats, and the janitor loop."""

    def __init__(
        self,
        base_dir: Path,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        janitor_interval_seconds: int = DEFAULT_JANITOR_INTERVAL_SECONDS,
    ) -> None:
        self.base_dir = base_dir
        self.ttl_seconds = ttl_seconds
        self.janitor_interval_seconds = janitor_interval_seconds
        self._sessions: dict[str, _Session] = {}
        self._server_to_session: dict[str, str] = {}
        self._janitor_task: Optional[asyncio.Task] = None
        self._now: Callable[[], datetime] = _utcnow
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def create_session(
        self, server_id: str, *, affected_regions: int = 0
    ) -> Path:
        """Tear down any prior session for ``server_id`` and create a fresh dir.

        Raises ``PreviewDiskGuardError`` if free space is below the heuristic.
        """
        required = max(affected_regions, 1) * AVG_REGION_BYTES * 2
        free = await self.disk_free_bytes()
        if free < required:
            raise PreviewDiskGuardError(free=free, required=required)

        prior = self._server_to_session.get(server_id)
        if prior is not None:
            await self.end(prior)

        session_id = secrets.token_hex(16)
        session_dir = self.base_dir / session_id
        await aioos.makedirs(session_dir, exist_ok=False)
        self._sessions[session_id] = _Session(
            session_id=session_id,
            server_id=server_id,
            base_dir=session_dir,
            last_seen=self._now(),
            affected_regions=affected_regions,
        )
        self._server_to_session[server_id] = session_id
        return session_dir

    def heartbeat(self, session_id: str) -> None:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise PreviewSessionNotFoundError(session_id)
        sess.last_seen = self._now()

    async def end(self, session_id: str) -> None:
        """Idempotent teardown."""
        sess = self._sessions.pop(session_id, None)
        if sess is None:
            return
        if sess.render_queue is not None:
            sess.render_queue.shutdown()
        # Don't clobber a server→session pointer a concurrent create_session may have replaced.
        existing = self._server_to_session.get(sess.server_id)
        if existing == session_id:
            self._server_to_session.pop(sess.server_id, None)
        await async_fs.rmtree(sess.base_dir, ignore_errors=True)

    def get_active_for_server(self, server_id: str) -> Optional[str]:
        return self._server_to_session.get(server_id)

    def get_session(self, session_id: str) -> Optional[_Session]:
        return self._sessions.get(session_id)

    def get_session_dir(self, session_id: str) -> Optional[Path]:
        sess = self._sessions.get(session_id)
        return sess.base_dir if sess else None

    async def get_tile_path(self, session_id: str, rx: int, rz: int) -> Optional[Path]:
        sess = self._sessions.get(session_id)
        if sess is None:
            return None
        candidate = sess.base_dir / "tiles" / f"r.{rx}.{rz}.png"
        return candidate if await aioos.path.exists(candidate) else None

    def attach_render_queue(
        self,
        session_id: str,
        *,
        queue: "ServerRenderQueue",
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
        return timedelta(seconds=self.ttl_seconds)

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
        known = {s.session_id for s in self._sessions.values()}
        deleted: list[Path] = []
        for child in await async_fs.iterdir(self.base_dir):
            if not await aioos.path.isdir(child):
                continue
            if child.name in known:
                continue
            await async_fs.rmtree(child, ignore_errors=True)
            deleted.append(child)
        return deleted

    async def janitor_loop(self) -> None:
        """Reap stale sessions and orphan dirs forever; tolerant of transient errors."""
        while True:
            try:
                await asyncio.sleep(self.janitor_interval_seconds)
                await self.reap_stale()
                await self.reap_orphan_dirs()
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
        except (asyncio.CancelledError, Exception):
            pass
