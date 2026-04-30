"""WorldRestoreOrchestrator: snapshot creation, eligibility, and restore flows.

This module owns the per-server restore state machine — lock acquisition,
safety-snapshot creation, scope-specific restore execution (world / dimension /
regions / chunks), and persistence of the ``Restoration`` row.

Endpoints (Session 3) consume the async generators of ``RestoreEvent`` and
``PreviewEvent`` returned by the public methods and stream them as SSE.

Preview lifecycle (heartbeat, janitor, disk guard) lives in
``app/world/preview.py`` and is exposed through this orchestrator's
``begin_preview`` / ``end_preview`` / ``heartbeat_preview`` methods.
"""

from __future__ import annotations

import asyncio
import secrets
import tempfile
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Callable,
    Iterable,
    Literal,
    Optional,
)

import aiofiles
import aiofiles.os as aioos
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dynamic_config import config as dynamic_config
from ..logger import logger
from ..mcmap import runner as mcmap_runner
from ..mcmap.cache import ServerMapCache
from ..mcmap.queue import ServerRenderQueue
from ..mcmap.types import MCMapError
from ..minecraft import DockerMCManager, MCServerStatus
from ..utils import async_fs
from ..models import (
    Restoration,
    RestorationSelection,
    RestorationStatus,
    RestorationType,
)
from ..snapshots.restic import ResticManager, ResticSnapshot, ResticSnapshotWithSummary
from .layout import DimensionInfo, WorldRoot, discover_world_roots
from .locks import (
    LockHolder,
    ServerOperationKind,
    ServerOperationLock,
)
from .preview import PreviewMapCache, PreviewSessionManager, PreviewSessionNotFoundError

SessionFactory = Callable[[], AsyncContextManager[AsyncSession]]

CHUNKS_PER_REGION_AXIS = 32
SUBDIR_KINDS = ("region", "entities", "poi")


# --- Public event models ----------------------------------------------------


class RestoreEvent(BaseModel):
    """SSE event emitted by ``begin_restore`` / ``rollback``."""

    event_type: Literal[
        "start",
        "safety_snapshot",
        "stage",
        "merge_region",
        "restore",
        "invalidate_cache",
        "complete",
        "error",
    ]
    message: Optional[str] = None
    percent: Optional[float] = None
    rx: Optional[int] = None
    rz: Optional[int] = None
    sub_dir: Optional[str] = None
    restoration_id: Optional[str] = None
    safety_snapshot_id: Optional[str] = None


class PreviewEvent(BaseModel):
    """SSE event emitted by ``begin_preview``."""

    event_type: Literal[
        "start",
        "stage",
        "merge_region",
        "render_progress",
        "ready",
        "error",
    ]
    message: Optional[str] = None
    session_id: Optional[str] = None
    percent: Optional[float] = None


# --- Errors -----------------------------------------------------------------


class RestoreError(Exception):
    """Generic restore-flow failure."""


class ServerNotStoppedError(RestoreError):
    """Raised when a restore is attempted while the target server is up."""


class SelectionResolutionError(RestoreError):
    """Raised when a selection cannot be resolved to filesystem paths."""


# --- Helpers ----------------------------------------------------------------


def _new_restoration_id() -> str:
    return secrets.token_hex(16)


def _group_chunks_by_region(
    chunks: Iterable[tuple[int, int]],
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Group absolute (cx, cz) chunk coords by region (rx, rz).

    Each value is the list of *region-relative* coords (0..31) for that region.
    """
    grouped: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for cx, cz in chunks:
        rx = cx // CHUNKS_PER_REGION_AXIS
        rz = cz // CHUNKS_PER_REGION_AXIS
        local_x = cx % CHUNKS_PER_REGION_AXIS
        local_z = cz % CHUNKS_PER_REGION_AXIS
        grouped.setdefault((rx, rz), []).append((local_x, local_z))
    return grouped


def _mcc_paths_for_region(
    region_dir: Path, rx: int, rz: int
) -> list[Path]:
    """All possible ``c.<absX>.<absZ>.mcc`` paths under ``region_dir`` for region (rx, rz).

    The restic include pattern picks them up if they exist; nonexistent
    includes are silently ignored.
    """
    paths: list[Path] = []
    base_x = rx * CHUNKS_PER_REGION_AXIS
    base_z = rz * CHUNKS_PER_REGION_AXIS
    for dx in range(CHUNKS_PER_REGION_AXIS):
        for dz in range(CHUNKS_PER_REGION_AXIS):
            paths.append(region_dir / f"c.{base_x + dx}.{base_z + dz}.mcc")
    return paths


async def _stage_destination(stage_dir: Path, live_path: Path) -> Path:
    """Where ``live_path`` will land under ``stage_dir`` after a restic restore."""
    return ResticManager.compute_restore_destination(
        stage_dir, await async_fs.resolve(live_path)
    )


# --- Orchestrator -----------------------------------------------------------


class WorldRestoreOrchestrator:
    """Coordinates world-restore flows for all four selection scopes.

    Construction takes explicit dependencies for testability; ``app/world/__init__.py``
    wires a singleton from the application's real managers.
    """

    def __init__(
        self,
        *,
        restic_manager: ResticManager,
        docker_mc_manager: DockerMCManager,
        server_operation_lock: ServerOperationLock,
        session_factory: SessionFactory,
        preview_base_dir: Optional[Path] = None,
        preview_ttl_seconds: Optional[int] = None,
        preview_janitor_interval_seconds: Optional[int] = None,
    ) -> None:
        self._restic = restic_manager
        self._docker = docker_mc_manager
        self._lock = server_operation_lock
        self._session_factory = session_factory
        base_dir = preview_base_dir or (
            Path(tempfile.gettempdir()) / "mc-admin-world-preview"
        )
        from .preview import DEFAULT_JANITOR_INTERVAL_SECONDS, DEFAULT_TTL_SECONDS

        self._preview_manager = PreviewSessionManager(
            base_dir=base_dir,
            ttl_seconds=preview_ttl_seconds or DEFAULT_TTL_SECONDS,
            janitor_interval_seconds=(
                preview_janitor_interval_seconds or DEFAULT_JANITOR_INTERVAL_SECONDS
            ),
        )

    # --- Snapshot creation -----------------------------------------------

    async def create_snapshot(
        self,
        server_id: str,
        selection: RestorationSelection,
        user_id: Optional[int],
    ) -> ResticSnapshotWithSummary:
        """Create a restic snapshot covering the selection paths.

        Acquires a BACKUP lock for the server. The HTTP-facing manual-snapshot
        endpoint only forwards WORLD / DIMENSION scopes; the REGIONS / CHUNKS
        branches remain reachable here so internal callers and tests can seed
        partial-coverage snapshots (e.g. for eligibility-filter assertions).
        Safety snapshots taken before a restore go through ``_restic.backup``
        directly inside ``begin_restore`` rather than this method, since they
        share the outer RESTORE lock.
        """
        paths = await self._resolve_paths_for_selection(server_id, selection)
        if not paths:
            raise SelectionResolutionError(
                f"selection resolved to no paths: {selection.model_dump()}"
            )
        holder = LockHolder(
            kind=ServerOperationKind.BACKUP,
            started_at=datetime.now(timezone.utc),
            user_id=user_id,
            description=f"world snapshot ({selection.type.value})",
        )
        async with self._lock.acquire(server_id, holder):
            return await self._restic.backup(paths)

    # --- Eligibility -----------------------------------------------------

    async def list_eligible_snapshots(
        self, server_id: str, selection: RestorationSelection
    ) -> list[ResticSnapshot]:
        """Return snapshots that cover every path the selection resolves to.

        Eligibility is checked against the MCA files only (and the world/
        dimension dirs for those scopes). The MCC sidecar paths emitted by
        ``_resolve_paths_for_selection`` are speculative include hints for
        restic — they cover the case where a region happens to have overflow
        chunks at the time of restore — but they are *not* required for a
        snapshot to qualify. Restic only records paths that actually existed
        at backup time, so most prior safety snapshots would carry zero or
        few of these speculative MCC paths in their ``paths`` field. Asking
        ``find_snapshots_covering`` to honor them filters out exactly the
        snapshots the user is most likely to need (their own safety snapshots).
        """
        paths = await self._resolve_eligibility_paths(server_id, selection)
        if not paths:
            return []
        return await self._restic.find_snapshots_covering(paths)

    # --- Restoration -----------------------------------------------------

    async def begin_restore(
        self,
        server_id: str,
        source_snapshot_id: str,
        selection: RestorationSelection,
        user_id: Optional[int],
        is_rollback: bool = False,
    ) -> AsyncGenerator[RestoreEvent, None]:
        """Run a full restore flow, yielding SSE events.

        Steps:
          1. Acquire RESTORE lock.
          2. Verify the server is stopped.
          3. Create a safety snapshot covering the same paths.
          4. Insert a ``Restoration`` row with status=running.
          5. Dispatch to the scope-specific flow.
          6. Update the row to succeeded/failed.
        """
        restoration_id = _new_restoration_id()
        holder = LockHolder(
            kind=ServerOperationKind.RESTORE,
            started_at=datetime.now(timezone.utc),
            user_id=user_id,
            description=f"world restore ({selection.type.value})"
            + (" rollback" if is_rollback else ""),
            restoration_id=restoration_id,
        )

        async with self._lock.acquire(server_id, holder):
            await self._ensure_server_stopped(server_id)
            paths = await self._resolve_paths_for_selection(server_id, selection)
            if not paths:
                raise SelectionResolutionError(
                    f"selection resolved to no paths: {selection.model_dump()}"
                )

            yield RestoreEvent(
                event_type="start",
                restoration_id=restoration_id,
                message=f"starting {selection.type.value} restore",
            )

            yield RestoreEvent(
                event_type="safety_snapshot",
                restoration_id=restoration_id,
                message="creating safety snapshot",
            )
            safety = await self._restic.backup(paths)
            safety_snapshot_id = safety.id
            yield RestoreEvent(
                event_type="safety_snapshot",
                restoration_id=restoration_id,
                safety_snapshot_id=safety_snapshot_id,
                message=f"safety snapshot {safety.short_id}",
            )

            await self._insert_restoration_row(
                restoration_id=restoration_id,
                server_id=server_id,
                selection=selection,
                source_snapshot_id=source_snapshot_id,
                safety_snapshot_id=safety_snapshot_id,
                is_rollback=is_rollback,
                user_id=user_id,
            )

            touched_items: list[str] = []
            try:
                if selection.type is RestorationType.CHUNKS:
                    async for ev in self._flow_chunks(
                        server_id=server_id,
                        source_snapshot_id=source_snapshot_id,
                        selection=selection,
                        restoration_id=restoration_id,
                    ):
                        yield ev
                else:
                    async for ev in self._flow_filesystem_restore(
                        source_snapshot_id=source_snapshot_id,
                        paths=paths,
                        restoration_id=restoration_id,
                        touched_items=touched_items,
                    ):
                        yield ev
            except Exception as exc:
                logger.exception(
                    "world restore failed: server=%s restoration=%s",
                    server_id,
                    restoration_id,
                )
                await self._update_restoration_row(
                    restoration_id, RestorationStatus.FAILED, str(exc)
                )
                yield RestoreEvent(
                    event_type="error",
                    restoration_id=restoration_id,
                    message=str(exc),
                )
                return

            invalidated = await self._invalidate_map_cache(
                server_id=server_id,
                selection=selection,
                touched_items=touched_items,
            )
            yield RestoreEvent(
                event_type="invalidate_cache",
                restoration_id=restoration_id,
                message=f"invalidated {invalidated} map tile(s)",
            )

            await self._update_restoration_row(
                restoration_id, RestorationStatus.SUCCEEDED, None
            )
            yield RestoreEvent(
                event_type="complete",
                restoration_id=restoration_id,
                message="restore complete",
            )

    async def rollback(
        self, restoration_id: str, user_id: Optional[int]
    ) -> AsyncGenerator[RestoreEvent, None]:
        """Roll back a prior restore by re-running with safety_snapshot as source."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Restoration).where(Restoration.id == restoration_id)
                )
            ).scalar_one_or_none()
        if row is None:
            raise RestoreError(f"restoration not found: {restoration_id}")
        if not row.safety_snapshot_id:
            raise RestoreError(
                f"restoration {restoration_id} has no safety snapshot to roll back to"
            )

        selection = RestorationSelection.model_validate_json(row.selection_json)
        async for ev in self.begin_restore(
            server_id=row.server_id,
            source_snapshot_id=row.safety_snapshot_id,
            selection=selection,
            user_id=user_id,
            is_rollback=True,
        ):
            yield ev

    # --- Preview lifecycle ----------------------------------------------

    async def begin_preview(
        self,
        server_id: str,
        source_snapshot_id: str,
        selection: RestorationSelection,
    ) -> AsyncGenerator[PreviewEvent, None]:
        """Stage snapshot MCAs into a /tmp session dir, run any chunk merge,
        and attach a lazy-render queue before emitting ``ready``.

        Tiles are *not* rendered eagerly — instead, the per-session
        ``ServerRenderQueue`` (mirroring the live-map pattern) renders each
        affected region on first tile request, with batching, coalescing of
        duplicate requests, and cancellation cascading to the mcmap
        subprocess when consumers disconnect. The render reuses the live
        world's palette (``data_path/.mcmap/palette.json``); if that's
        missing the SSE emits an ``error`` event prompting the user to
        initialize the live map first.
        """
        paths = await self._resolve_paths_for_selection(server_id, selection)
        if not paths:
            raise SelectionResolutionError(
                f"selection resolved to no paths: {selection.model_dump()}"
            )

        affected_regions = _count_affected_regions(selection)
        session_dir = await self._preview_manager.create_session(
            server_id, affected_regions=affected_regions
        )
        session_id = session_dir.name

        try:
            yield PreviewEvent(
                event_type="start",
                session_id=session_id,
                message=f"preview staging from snapshot {source_snapshot_id[:8]}",
            )
            await aioos.makedirs(session_dir / "source", exist_ok=True)
            async for _ in self._restic.restore(
                snapshot_id=source_snapshot_id,
                target_path=session_dir / "source",
                include_paths=paths,
            ):
                pass
            yield PreviewEvent(
                event_type="stage",
                session_id=session_id,
                message="snapshot MCAs staged",
            )

            if selection.type is RestorationType.CHUNKS:
                async for ev in self._preview_chunk_merge(
                    server_id=server_id,
                    selection=selection,
                    session_dir=session_dir,
                    session_id=session_id,
                ):
                    yield ev

            if selection.type in (RestorationType.REGIONS, RestorationType.CHUNKS):
                await self._attach_preview_render_queue(
                    server_id=server_id,
                    selection=selection,
                    session_dir=session_dir,
                    session_id=session_id,
                )

            yield PreviewEvent(
                event_type="ready",
                session_id=session_id,
                message="preview ready",
            )
        except Exception as exc:
            logger.exception("preview failed for server=%s", server_id)
            await self._preview_manager.end(session_id)
            yield PreviewEvent(
                event_type="error",
                session_id=session_id,
                message=str(exc),
            )

    async def _preview_chunk_merge(
        self,
        *,
        server_id: str,
        selection: RestorationSelection,
        session_dir: Path,
        session_id: str,
    ) -> AsyncGenerator[PreviewEvent, None]:
        """Copy live MCAs into a preview/ subdir, then merge selected chunks
        from the staged snapshot. The live world is never touched."""
        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()
        roots = await discover_world_roots(data_path)
        if selection.region_dir_relpath is None:
            raise SelectionResolutionError(
                "chunks selection requires region_dir_relpath"
            )
        dim = _find_dimension(data_path, roots, selection.region_dir_relpath)

        grouped = _group_chunks_by_region(selection.chunks)
        live_subdirs: dict[str, Optional[Path]] = {
            "region": dim.region_dir,
            "entities": dim.entities_dir,
            "poi": dim.poi_dir,
        }

        preview_dir = session_dir / "preview"
        total = len(grouped) * sum(1 for v in live_subdirs.values() if v is not None)
        done = 0
        for (rx, rz), local_chunks in grouped.items():
            for sub, live_dir in live_subdirs.items():
                if live_dir is None:
                    continue
                live_mca = live_dir / f"r.{rx}.{rz}.mca"
                staged_mca = await _stage_destination(
                    session_dir / "source", live_mca
                )
                preview_subdir = await _stage_destination(preview_dir, live_dir)
                await aioos.makedirs(preview_subdir, exist_ok=True)
                preview_mca = preview_subdir / f"r.{rx}.{rz}.mca"

                if await aioos.path.exists(live_mca):
                    await async_fs.copy2(live_mca, preview_mca)
                if await aioos.path.exists(staged_mca):
                    if not await aioos.path.exists(preview_mca):
                        # Live had no copy of this region but snapshot does — start
                        # the preview from an empty file to give mcmap a target.
                        async with aiofiles.open(preview_mca, "wb") as f:
                            await f.write(b"\x00" * 8192)
                    await self._merge_replace(
                        source_mca=staged_mca,
                        target_mca=preview_mca,
                        chunks=local_chunks,
                        owned_by=data_path,
                    )
                elif await aioos.path.exists(preview_mca):
                    await self._merge_remove(
                        target_mca=preview_mca,
                        chunks=local_chunks,
                        owned_by=data_path,
                    )
                done += 1
                yield PreviewEvent(
                    event_type="merge_region",
                    session_id=session_id,
                    percent=(done / total) * 100.0 if total else 100.0,
                )

    async def _attach_preview_render_queue(
        self,
        *,
        server_id: str,
        selection: RestorationSelection,
        session_dir: Path,
        session_id: str,
    ) -> None:
        """Build a per-session ``ServerRenderQueue`` and attach it to the
        preview session. Tiles are rendered lazily on first request.

        Source MCAs live under ``preview/`` for chunk-scope (the chunk-merged
        copies) and ``source/`` for region-scope (the snapshot's regions,
        untouched). Output PNGs land at ``<session_dir>/tiles/r.<rx>.<rz>.png``
        — the path ``PreviewSessionManager.get_tile_path`` checks. The queue
        reuses the live world's palette so we don't need a separate
        download/palette step per preview.
        """
        if selection.region_dir_relpath is None:
            return

        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()
        cache = ServerMapCache(data_path=data_path)
        if not await aioos.path.exists(cache.palette_json):
            raise RestoreError(
                "Cannot render preview: live map palette is not initialized; "
                "open the world map page and run initialization first."
            )

        roots = await discover_world_roots(data_path)
        dim = _find_dimension(data_path, roots, selection.region_dir_relpath)
        live_region_dir = dim.region_dir

        if selection.type is RestorationType.CHUNKS:
            source_root = session_dir / "preview"
            grouped = _group_chunks_by_region(selection.chunks)
            affected_iter = list(grouped.keys())
        else:
            source_root = session_dir / "source"
            affected_iter = list(set(selection.regions))

        staged_region_dir = await _stage_destination(source_root, live_region_dir)
        affected_keys: set[tuple[int, int]] = set()
        for (rx, rz) in affected_iter:
            mca = staged_region_dir / f"r.{rx}.{rz}.mca"
            if await aioos.path.exists(mca):
                affected_keys.add((rx, rz))

        if not affected_keys:
            return

        tiles_dir = session_dir / "tiles"
        await aioos.makedirs(tiles_dir, exist_ok=True)

        preview_cache = PreviewMapCache(
            palette_json=cache.palette_json,
            data_path=data_path,
            staged_region_dir=staged_region_dir,
            tiles_root=tiles_dir,
        )
        queue = ServerRenderQueue(
            server_name=session_id,
            region_path=selection.region_dir_relpath,
            cache=preview_cache,  # type: ignore[arg-type]
        )
        self._preview_manager.attach_render_queue(
            session_id, queue=queue, affected_keys=affected_keys
        )

    async def end_preview(self, session_id: str) -> None:
        await self._preview_manager.end(session_id)

    def heartbeat_preview(self, session_id: str) -> None:
        self._preview_manager.heartbeat(session_id)

    async def get_preview_tile(
        self, session_id: str, rx: int, rz: int
    ) -> Optional[Path]:
        return await self._preview_manager.get_tile_path(session_id, rx, rz)

    async def request_preview_tile(
        self, session_id: str, rx: int, rz: int, *, timeout: Optional[float] = None
    ) -> Path:
        """Resolve a preview tile, lazily rendering on first miss.

        Fast path: returns the file path if the tile is already rendered.
        Otherwise, enqueues a render request on the session's per-dimension
        ``ServerRenderQueue`` and awaits its completion (subject to
        ``timeout``, defaulting to ``config.mcmap.request_timeout_seconds``).

        Raises ``PreviewSessionNotFoundError`` when the session is unknown,
        ``FileNotFoundError`` when the tile lies outside the staged
        affected-region set, and ``asyncio.TimeoutError`` on render timeout.
        """
        sess = self._preview_manager.get_session(session_id)
        if sess is None:
            raise PreviewSessionNotFoundError(session_id)

        png = sess.base_dir / "tiles" / f"r.{rx}.{rz}.png"
        if await aioos.path.exists(png):
            return png

        queue = sess.render_queue
        if queue is None:
            raise FileNotFoundError(
                f"preview tile ({rx}, {rz}) not available — render queue not attached"
            )
        if sess.affected_keys is not None and (rx, rz) not in sess.affected_keys:
            raise FileNotFoundError(
                f"preview tile ({rx}, {rz}) is outside the preview's affected region set"
            )

        effective_timeout = (
            timeout
            if timeout is not None
            else float(dynamic_config.mcmap.request_timeout_seconds)
        )
        return await asyncio.wait_for(queue.request(rx, rz), timeout=effective_timeout)

    def get_preview_session_dir(self, session_id: str) -> Optional[Path]:
        """Expose the staged source/preview dirs for the tile-render endpoint."""
        return self._preview_manager.get_session_dir(session_id)

    def start_janitor(self) -> "asyncio.Task":
        return self._preview_manager.start_janitor()

    async def stop_janitor(self) -> None:
        await self._preview_manager.stop_janitor()

    # --- Internal flow methods -------------------------------------------

    async def _flow_filesystem_restore(
        self,
        *,
        source_snapshot_id: str,
        paths: list[Path],
        restoration_id: str,
        touched_items: list[str],
    ) -> AsyncGenerator[RestoreEvent, None]:
        """In-place restic restore for world / dimension / regions scopes.

        Yields one ``restore`` event at the start and additional
        ``restore`` events with ``percent`` set on each restic ``status``
        update. ``touched_items`` is filled with the absolute paths of
        files restic actually wrote (or deleted) — used by the caller to
        compute PNG invalidations.
        """
        yield RestoreEvent(
            event_type="restore",
            restoration_id=restoration_id,
            message=f"restoring {len(paths)} path(s) from snapshot {source_snapshot_id[:8]}",
            percent=0.0,
        )
        async for ev in self._restic.restore(
            snapshot_id=source_snapshot_id,
            target_path=Path("/"),
            include_paths=paths,
        ):
            if ev.kind == "status" and ev.percent_done is not None:
                yield RestoreEvent(
                    event_type="restore",
                    restoration_id=restoration_id,
                    percent=ev.percent_done * 100.0,
                )
            elif ev.kind == "file" and ev.action in ("updated", "restored", "deleted"):
                if ev.item is not None:
                    touched_items.append(ev.item)

    async def _flow_chunks(
        self,
        *,
        server_id: str,
        source_snapshot_id: str,
        selection: RestorationSelection,
        restoration_id: str,
    ) -> AsyncGenerator[RestoreEvent, None]:
        """Stage source MCAs to a temp dir, then merge selected chunks per region."""
        if not selection.chunks:
            return
        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()
        roots = await discover_world_roots(data_path)
        if selection.region_dir_relpath is None:
            raise SelectionResolutionError(
                "chunks selection requires region_dir_relpath"
            )
        dim = _find_dimension(data_path, roots, selection.region_dir_relpath)

        grouped = _group_chunks_by_region(selection.chunks)
        live_subdirs: dict[str, Optional[Path]] = {
            "region": dim.region_dir,
            "entities": dim.entities_dir,
            "poi": dim.poi_dir,
        }

        # Build the include-path list for the staging restore.
        include_paths: list[Path] = []
        for (rx, rz) in grouped:
            for sub in SUBDIR_KINDS:
                live_dir = live_subdirs.get(sub)
                if live_dir is None:
                    continue
                include_paths.append(live_dir / f"r.{rx}.{rz}.mca")
                # 1024 possible mcc companions per region — restic ignores
                # nonexistent includes.
                include_paths.extend(_mcc_paths_for_region(live_dir, rx, rz))

        async with AsyncExitStack() as stack:
            stage_root = Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="mc-admin-restore-stage-")
                )
            )
            yield RestoreEvent(
                event_type="stage",
                restoration_id=restoration_id,
                message=f"staging {len(grouped)} region(s) from snapshot {source_snapshot_id[:8]}",
                percent=0.0,
            )
            async for ev in self._restic.restore(
                snapshot_id=source_snapshot_id,
                target_path=stage_root,
                include_paths=include_paths,
            ):
                if ev.kind == "status" and ev.percent_done is not None:
                    yield RestoreEvent(
                        event_type="stage",
                        restoration_id=restoration_id,
                        percent=ev.percent_done * 100.0,
                    )

            total_jobs = len(grouped) * sum(
                1 for live in live_subdirs.values() if live is not None
            )
            done = 0
            for (rx, rz), local_chunks in grouped.items():
                for sub in SUBDIR_KINDS:
                    live_dir = live_subdirs.get(sub)
                    if live_dir is None:
                        continue
                    live_mca = live_dir / f"r.{rx}.{rz}.mca"
                    staged_mca = await _stage_destination(stage_root, live_mca)
                    if await aioos.path.exists(staged_mca):
                        await self._merge_replace(
                            source_mca=staged_mca,
                            target_mca=live_mca,
                            chunks=local_chunks,
                            owned_by=data_path,
                        )
                    else:
                        if not await aioos.path.exists(live_mca):
                            done += 1
                            continue
                        await self._merge_remove(
                            target_mca=live_mca,
                            chunks=local_chunks,
                            owned_by=data_path,
                        )
                    done += 1
                    yield RestoreEvent(
                        event_type="merge_region",
                        restoration_id=restoration_id,
                        rx=rx,
                        rz=rz,
                        sub_dir=sub,
                        percent=(done / total_jobs) * 100.0 if total_jobs else 100.0,
                    )

    async def _run_chunk_op(
        self,
        *,
        op_name: str,
        ctx_manager: Any,
        count_key: str,
        expected_count: int,
    ) -> None:
        async with ctx_manager as proc:
            terminal: Optional[dict] = None
            async for event in proc:
                etype = event.get("type")
                if etype == "result":
                    terminal = event
                elif etype == "error":
                    raise MCMapError(event.get("message", f"{op_name} failed"))
        if proc.returncode != 0:
            raise MCMapError(f"mcmap {op_name} exited with {proc.returncode}")
        if terminal is None or terminal.get(count_key) != expected_count:
            raise MCMapError(
                f"mcmap {op_name} reported {terminal} for {expected_count} requested chunks"
            )

    async def _merge_replace(
        self,
        *,
        source_mca: Path,
        target_mca: Path,
        chunks: list[tuple[int, int]],
        owned_by: Path,
    ) -> None:
        await self._run_chunk_op(
            op_name="replace-chunks",
            ctx_manager=mcmap_runner.replace_chunks(
                source_mca=source_mca,
                target_mca=target_mca,
                chunks=chunks,
                owned_by=owned_by,
            ),
            count_key="replaced",
            expected_count=len(chunks),
        )

    async def _merge_remove(
        self,
        *,
        target_mca: Path,
        chunks: list[tuple[int, int]],
        owned_by: Path,
    ) -> None:
        await self._run_chunk_op(
            op_name="remove-chunks",
            ctx_manager=mcmap_runner.remove_chunks(
                target_mca=target_mca,
                chunks=chunks,
                owned_by=owned_by,
            ),
            count_key="removed",
            expected_count=len(chunks),
        )

    # --- Cache invalidation ---------------------------------------------

    async def _invalidate_map_cache(
        self,
        *,
        server_id: str,
        selection: RestorationSelection,
        touched_items: list[str],
    ) -> int:
        """Delete cached PNG tiles whose source MCA was modified by this restore.

        - WORLD / DIMENSION (filesystem restore): derive affected regions
          from ``touched_items`` (restic verbose_status output). This handles
          arbitrary multi-root layouts because the cache key is just the
          MCA's parent dir relpath under ``data_path``.
        - REGIONS / CHUNKS: derive directly from the selection. Restic items
          would also work for REGIONS but the selection is the source of
          truth and avoids any parsing.
        """
        from . import png_invalidate

        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()

        if selection.type in (RestorationType.WORLD, RestorationType.DIMENSION):
            pngs = png_invalidate.pngs_for_restic_items(data_path, touched_items)
        elif selection.type is RestorationType.REGIONS:
            if selection.region_dir_relpath is None:
                return 0
            pngs = png_invalidate.pngs_for_regions(
                data_path, selection.region_dir_relpath, set(selection.regions)
            )
        elif selection.type is RestorationType.CHUNKS:
            if selection.region_dir_relpath is None:
                return 0
            grouped = _group_chunks_by_region(selection.chunks)
            pngs = png_invalidate.pngs_for_regions(
                data_path, selection.region_dir_relpath, set(grouped.keys())
            )
        else:
            return 0

        if not pngs:
            return 0
        return await png_invalidate.delete_pngs(pngs)

    # --- Path resolution -------------------------------------------------

    async def _resolve_paths_core(
        self,
        server_id: str,
        selection: RestorationSelection,
        *,
        include_mcc: bool,
    ) -> list[Path]:
        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()
        roots = await discover_world_roots(data_path)
        if not roots:
            return []

        if selection.type is RestorationType.WORLD:
            return [root.path for root in roots]

        if selection.region_dir_relpath is None:
            raise SelectionResolutionError(
                f"selection type '{selection.type.value}' requires region_dir_relpath"
            )
        dim = _find_dimension(data_path, roots, selection.region_dir_relpath)

        if selection.type is RestorationType.DIMENSION:
            paths = [dim.region_dir]
            if dim.entities_dir is not None:
                paths.append(dim.entities_dir)
            if dim.poi_dir is not None:
                paths.append(dim.poi_dir)
            return paths

        expand = _expand_region_paths if include_mcc else _expand_region_mca_paths

        if selection.type is RestorationType.REGIONS:
            return expand(dim, selection.regions)

        if selection.type is RestorationType.CHUNKS:
            grouped = _group_chunks_by_region(selection.chunks)
            return expand(dim, list(grouped.keys()))

        raise SelectionResolutionError(f"unsupported selection type: {selection.type}")

    async def _resolve_paths_for_selection(
        self, server_id: str, selection: RestorationSelection
    ) -> list[Path]:
        return await self._resolve_paths_core(server_id, selection, include_mcc=True)

    async def _resolve_eligibility_paths(
        self, server_id: str, selection: RestorationSelection
    ) -> list[Path]:
        """Like ``_resolve_paths_for_selection`` but without speculative MCC
        sidecars — only the MCA files a snapshot must cover to qualify.
        """
        return await self._resolve_paths_core(server_id, selection, include_mcc=False)

    # --- Server-state guard ---------------------------------------------

    async def _ensure_server_stopped(self, server_id: str) -> None:
        instance = self._docker.get_instance(server_id)
        status = await instance.get_status()
        if status in (
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ):
            raise ServerNotStoppedError(
                f"server '{server_id}' must be stopped before restore (current status: {status.value})"
            )

    # --- DB helpers ------------------------------------------------------

    async def _insert_restoration_row(
        self,
        *,
        restoration_id: str,
        server_id: str,
        selection: RestorationSelection,
        source_snapshot_id: str,
        safety_snapshot_id: Optional[str],
        is_rollback: bool,
        user_id: Optional[int],
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                Restoration(
                    id=restoration_id,
                    server_id=server_id,
                    type=selection.type,
                    source_snapshot_id=source_snapshot_id,
                    safety_snapshot_id=safety_snapshot_id,
                    selection_json=selection.model_dump_json(),
                    is_rollback=is_rollback,
                    initiated_by_user_id=user_id,
                )
            )
            await session.commit()

    async def _update_restoration_row(
        self,
        restoration_id: str,
        status: RestorationStatus,
        error_message: Optional[str],
    ) -> None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Restoration).where(Restoration.id == restoration_id)
                )
            ).scalar_one_or_none()
            if row is None:
                logger.warning("restoration row %s missing on update", restoration_id)
                return
            row.status = status
            row.finished_at = datetime.now(timezone.utc)
            if error_message is not None:
                row.error_message = error_message
            await session.commit()


# --- Module-level helpers ----------------------------------------------


def _find_dimension(
    data_path: Path,
    roots: list[WorldRoot],
    region_dir_relpath: str,
) -> DimensionInfo:
    """Locate a dimension across all world roots by its data-relative path."""
    target = Path(region_dir_relpath)
    for root in roots:
        for dim in root.dimensions:
            try:
                if dim.region_dir.relative_to(data_path) == target:
                    return dim
            except ValueError:
                continue
    raise SelectionResolutionError(
        f"dimension with region_dir_relpath '{region_dir_relpath}' not found"
    )


def _expand_region_paths(
    dim: DimensionInfo, regions: list[tuple[int, int]]
) -> list[Path]:
    """Produce the include-path list for a regions/chunks restore."""
    paths: list[Path] = []
    for (rx, rz) in regions:
        for live_dir in (dim.region_dir, dim.entities_dir, dim.poi_dir):
            if live_dir is None:
                continue
            paths.append(live_dir / f"r.{rx}.{rz}.mca")
            paths.extend(_mcc_paths_for_region(live_dir, rx, rz))
    return paths


def _expand_region_mca_paths(
    dim: DimensionInfo, regions: list[tuple[int, int]]
) -> list[Path]:
    """MCA-only variant of ``_expand_region_paths`` — used for snapshot
    eligibility checks where speculative MCC sidecars would over-filter
    (restic doesn't record paths that didn't exist at backup time)."""
    paths: list[Path] = []
    for (rx, rz) in regions:
        for live_dir in (dim.region_dir, dim.entities_dir, dim.poi_dir):
            if live_dir is None:
                continue
            paths.append(live_dir / f"r.{rx}.{rz}.mca")
    return paths


def _count_affected_regions(selection: RestorationSelection) -> int:
    """Used by the disk-guard heuristic in PreviewSessionManager."""
    if selection.type is RestorationType.REGIONS:
        return len(selection.regions)
    if selection.type is RestorationType.CHUNKS:
        return len({(c[0] // CHUNKS_PER_REGION_AXIS, c[1] // CHUNKS_PER_REGION_AXIS) for c in selection.chunks})
    # WORLD/DIMENSION are ambiguous — caller has to scan disk for an exact count.
    # Use a conservative default so the disk guard doesn't trip on typical setups.
    return 16


