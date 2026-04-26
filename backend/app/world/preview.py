"""Per-server world-restore preview session lifecycle.

A *preview* is a time-bounded staging area in /tmp where snapshot MCAs (and
optionally chunk-merged MCAs, for the CHUNKS scope) are rendered to PNG tiles
the frontend can display alongside the live map. Each server may have at most
one active preview session at a time.

Responsibilities of this module:
  - Create and tear down session directories.
  - Track ``last_seen`` timestamps; heartbeat on tile fetches/explicit ping.
  - Run a janitor loop that reaps stale sessions and orphan dirs.
  - Refuse new sessions when free disk space is below a threshold.
  - Be entirely thread-/cancellation-safe; ``end`` is idempotent.

The orchestrator (``app/world/restore.py``) owns a ``PreviewSessionManager``
instance and uses it to drive ``begin_preview`` / ``heartbeat_preview`` /
``end_preview`` / ``get_preview_tile``. Endpoints are added in Session 3.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 600  # 10 minutes
DEFAULT_JANITOR_INTERVAL_SECONDS = 60
AVG_REGION_BYTES = 8 * 1024 * 1024  # ~8 MiB per region — heuristic for disk guard


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PreviewSessionManager:
    """Manages /tmp preview session directories, heartbeats, and the janitor loop.

    Construction takes the base directory (created on first use) and a TTL.
    The manager itself is *not* an async context manager — janitor lifecycle
    is exposed via ``start_janitor`` / ``stop_janitor``.
    """

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

    # --- Session lifecycle ------------------------------------------------

    def create_session(self, server_id: str, *, affected_regions: int = 0) -> Path:
        """Create a new session directory for ``server_id`` and tear down the prior
        session for the same server (if any). Returns the session dir.

        Raises ``PreviewDiskGuardError`` if estimated requirement exceeds free space.
        """
        required = max(affected_regions, 1) * AVG_REGION_BYTES * 2
        free = self.disk_free_bytes()
        if free < required:
            raise PreviewDiskGuardError(free=free, required=required)

        prior = self._server_to_session.get(server_id)
        if prior is not None:
            self.end(prior)

        session_id = secrets.token_hex(16)
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=False)
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

    def end(self, session_id: str) -> None:
        """Tear down a session. Idempotent — never fails if session is already gone."""
        sess = self._sessions.pop(session_id, None)
        if sess is None:
            return
        # Drop the server→session pointer only if it still points at this session
        # (a concurrent create_session may have replaced it).
        existing = self._server_to_session.get(sess.server_id)
        if existing == session_id:
            self._server_to_session.pop(sess.server_id, None)
        shutil.rmtree(sess.base_dir, ignore_errors=True)

    def get_active_for_server(self, server_id: str) -> Optional[str]:
        return self._server_to_session.get(server_id)

    def get_session_dir(self, session_id: str) -> Optional[Path]:
        sess = self._sessions.get(session_id)
        return sess.base_dir if sess else None

    def get_tile_path(self, session_id: str, rx: int, rz: int) -> Optional[Path]:
        sess = self._sessions.get(session_id)
        if sess is None:
            return None
        candidate = sess.base_dir / "tiles" / f"r.{rx}.{rz}.png"
        return candidate if candidate.exists() else None

    # --- Disk + janitor --------------------------------------------------

    def disk_free_bytes(self) -> int:
        return shutil.disk_usage(self.base_dir).free

    def _ttl(self) -> timedelta:
        return timedelta(seconds=self.ttl_seconds)

    def reap_stale(self) -> list[str]:
        """End every session whose ``last_seen`` is older than the TTL. Returns
        the session_ids that were ended.
        """
        cutoff = self._now() - self._ttl()
        stale = [sid for sid, s in self._sessions.items() if s.last_seen < cutoff]
        for sid in stale:
            self.end(sid)
        return stale

    def reap_orphan_dirs(self) -> list[Path]:
        """Delete subdirectories of ``base_dir`` that don't correspond to a known
        session — these are orphans from a crashed prior process or a manual
        leftover. Returns the deleted paths.
        """
        if not self.base_dir.exists():
            return []
        known = {s.session_id for s in self._sessions.values()}
        deleted: list[Path] = []
        for child in self.base_dir.iterdir():
            if not child.is_dir():
                continue
            if child.name in known:
                continue
            try:
                shutil.rmtree(child, ignore_errors=True)
                deleted.append(child)
            except OSError:
                logger.exception("preview: failed to remove orphan %s", child)
        return deleted

    async def janitor_loop(self) -> None:
        """Run forever; cancel the task to stop. Safe against transient errors."""
        while True:
            try:
                await asyncio.sleep(self.janitor_interval_seconds)
                self.reap_stale()
                self.reap_orphan_dirs()
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

