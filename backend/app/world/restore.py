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

import secrets
import tempfile
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    AsyncContextManager,
    AsyncGenerator,
    Callable,
    Iterable,
    Literal,
    Optional,
)

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logger import logger
from ..mcmap import runner as mcmap_runner
from ..mcmap.types import MCMapError
from ..minecraft import DockerMCManager, MCServerStatus
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


def _stage_destination(stage_dir: Path, live_path: Path) -> Path:
    """Where ``live_path`` will land under ``stage_dir`` after a restic restore."""
    return ResticManager.compute_restore_destination(stage_dir, live_path.resolve())


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
    ) -> None:
        self._restic = restic_manager
        self._docker = docker_mc_manager
        self._lock = server_operation_lock
        self._session_factory = session_factory
        self._preview_base_dir = preview_base_dir or Path(tempfile.gettempdir()) / "mc-admin-world-preview"

    # --- Snapshot creation -----------------------------------------------

    async def create_snapshot(
        self,
        server_id: str,
        selection: RestorationSelection,
        user_id: Optional[int],
    ) -> ResticSnapshotWithSummary:
        """Create a restic snapshot covering the selection paths.

        Acquires a BACKUP lock for the server. Used for ad-hoc world snapshots
        (e.g. user clicking "Snapshot now" in the world-restore UI) — distinct
        from cron-driven backups.
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
        """Return snapshots that cover every path the selection resolves to."""
        paths = await self._resolve_paths_for_selection(server_id, selection)
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
          3. Create a safety snapshot covering the same paths (skipped on rollback).
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

            safety_snapshot_id: Optional[str] = None
            if not is_rollback:
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

    # --- Preview (skeleton; Phase 7 fleshes it out) ----------------------

    async def begin_preview(
        self,
        server_id: str,
        source_snapshot_id: str,
        selection: RestorationSelection,
    ) -> AsyncGenerator[PreviewEvent, None]:  # pragma: no cover — Phase 7
        raise NotImplementedError("preview lifecycle is implemented in Phase 7")
        yield  # pragma: no cover

    async def end_preview(self, session_id: str) -> None:  # pragma: no cover
        raise NotImplementedError("preview lifecycle is implemented in Phase 7")

    async def heartbeat_preview(self, session_id: str) -> None:  # pragma: no cover
        raise NotImplementedError("preview lifecycle is implemented in Phase 7")

    def get_preview_tile(
        self, session_id: str, rx: int, rz: int
    ) -> Optional[Path]:  # pragma: no cover
        raise NotImplementedError("preview lifecycle is implemented in Phase 7")

    # --- Internal flow methods -------------------------------------------

    async def _flow_filesystem_restore(
        self,
        *,
        source_snapshot_id: str,
        paths: list[Path],
        restoration_id: str,
    ) -> AsyncGenerator[RestoreEvent, None]:
        """In-place restic restore for world / dimension / regions scopes."""
        yield RestoreEvent(
            event_type="restore",
            restoration_id=restoration_id,
            message=f"restoring {len(paths)} path(s) from snapshot {source_snapshot_id[:8]}",
        )
        await self._restic.restore(
            snapshot_id=source_snapshot_id,
            target_path=Path("/"),
            include_paths=paths,
        )

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
        root, dim = _find_root_and_dimension(roots, selection)

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
            )
            await self._restic.restore(
                snapshot_id=source_snapshot_id,
                target_path=stage_root,
                include_paths=include_paths,
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
                    staged_mca = _stage_destination(stage_root, live_mca)
                    if staged_mca.exists():
                        await self._merge_replace(
                            source_mca=staged_mca,
                            target_mca=live_mca,
                            chunks=local_chunks,
                            owned_by=data_path,
                        )
                    else:
                        if not live_mca.exists():
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

        del root  # match value not needed past dimension lookup

    async def _merge_replace(
        self,
        *,
        source_mca: Path,
        target_mca: Path,
        chunks: list[tuple[int, int]],
        owned_by: Path,
    ) -> None:
        async with mcmap_runner.replace_chunks(
            source_mca=source_mca,
            target_mca=target_mca,
            chunks=chunks,
            owned_by=owned_by,
        ) as proc:
            terminal: Optional[dict] = None
            async for event in proc:
                etype = event.get("type")
                if etype == "result":
                    terminal = event
                elif etype == "error":
                    raise MCMapError(event.get("message", "replace_chunks failed"))
        if proc.returncode != 0:
            raise MCMapError(
                f"mcmap replace-chunks exited with {proc.returncode} (target={target_mca})"
            )
        if terminal is None or terminal.get("replaced") != len(chunks):
            raise MCMapError(
                f"mcmap replace-chunks reported {terminal} for {len(chunks)} requested chunks"
            )

    async def _merge_remove(
        self,
        *,
        target_mca: Path,
        chunks: list[tuple[int, int]],
        owned_by: Path,
    ) -> None:
        async with mcmap_runner.remove_chunks(
            target_mca=target_mca,
            chunks=chunks,
            owned_by=owned_by,
        ) as proc:
            terminal: Optional[dict] = None
            async for event in proc:
                etype = event.get("type")
                if etype == "result":
                    terminal = event
                elif etype == "error":
                    raise MCMapError(event.get("message", "remove_chunks failed"))
        if proc.returncode != 0:
            raise MCMapError(
                f"mcmap remove-chunks exited with {proc.returncode} (target={target_mca})"
            )
        if terminal is None or terminal.get("removed") != len(chunks):
            raise MCMapError(
                f"mcmap remove-chunks reported {terminal} for {len(chunks)} requested chunks"
            )

    # --- Path resolution -------------------------------------------------

    async def _resolve_paths_for_selection(
        self, server_id: str, selection: RestorationSelection
    ) -> list[Path]:
        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()
        roots = await discover_world_roots(data_path)
        if not roots:
            return []

        if selection.type is RestorationType.WORLD:
            return [root.path for root in roots]

        root, dim = _find_root_and_dimension(roots, selection)

        if selection.type is RestorationType.DIMENSION:
            paths = [dim.region_dir]
            if dim.entities_dir is not None:
                paths.append(dim.entities_dir)
            if dim.poi_dir is not None:
                paths.append(dim.poi_dir)
            return paths

        if selection.type is RestorationType.REGIONS:
            return _expand_region_paths(dim, selection.regions)

        if selection.type is RestorationType.CHUNKS:
            grouped = _group_chunks_by_region(selection.chunks)
            return _expand_region_paths(dim, list(grouped.keys()))

        raise SelectionResolutionError(f"unsupported selection type: {selection.type}")

    # --- Server-state guard ---------------------------------------------

    async def _ensure_server_stopped(self, server_id: str) -> None:
        instance = self._docker.get_instance(server_id)
        status = await instance.get_status()
        if status not in (MCServerStatus.REMOVED, MCServerStatus.EXISTS):
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


def _find_root_and_dimension(
    roots: list[WorldRoot], selection: RestorationSelection
) -> tuple[WorldRoot, DimensionInfo]:
    target_root = next(
        (r for r in roots if r.name == selection.world_root_name), None
    )
    if target_root is None:
        raise SelectionResolutionError(
            f"world root '{selection.world_root_name}' not found"
        )

    target_dim: Optional[DimensionInfo] = None
    if selection.dimension_label:
        target_dim = next(
            (d for d in target_root.dimensions if d.label == selection.dimension_label),
            None,
        )
    elif selection.region_dir_relpath:
        # Fallback match by region_dir relpath (frontend may send either).
        for d in target_root.dimensions:
            try:
                if d.region_dir.resolve().match(selection.region_dir_relpath):
                    target_dim = d
                    break
            except Exception:
                continue

    if target_dim is None:
        raise SelectionResolutionError(
            f"dimension '{selection.dimension_label}' not found under "
            f"world root '{selection.world_root_name}'"
        )
    return target_root, target_dim


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


