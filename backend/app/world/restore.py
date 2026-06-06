"""WorldRestoreOrchestrator: lock, safety snapshot, scope-specific restore, persistence.

Public methods return async generators of ``RestoreEvent`` / ``PreviewEvent``
that the routers stream as SSE. Preview heartbeat/janitor/disk-guard lives in
``app/world/preview.py``.
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
from ..mcmap.events import (
    MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER,
    MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER,
    MCMapErrorEvent,
    MCMapRemoveChunksResultEvent,
    MCMapReplaceChunksResultEvent,
)
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
PREVIEW_BASE_DIR = Path(tempfile.gettempdir()) / "mc-admin-world-restore"
RESTORATION_TYPE_LABELS = {
    RestorationType.WORLD: "整个世界",
    RestorationType.DIMENSION: "维度",
    RestorationType.REGIONS: "区域",
    RestorationType.CHUNKS: "区块",
}


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


class RestoreError(Exception):
    pass


class ServerNotStoppedError(RestoreError):
    """Raised when a restore is attempted while the target server is up."""


class SelectionResolutionError(RestoreError):
    """Raised when a selection cannot be resolved to filesystem paths."""


def _new_restoration_id() -> str:
    return secrets.token_hex(16)


def _selection_label(selection: RestorationSelection) -> str:
    return RESTORATION_TYPE_LABELS.get(selection.type, selection.type.value)


def _group_chunks_by_region(
    chunks: Iterable[tuple[int, int]],
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Group absolute ``(cx, cz)`` by region; values are region-relative ``0..31`` coords."""
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
    """Speculative ``c.<absX>.<absZ>.mcc`` paths; restic ignores ones that don't exist."""
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


class WorldRestoreOrchestrator:
    """Coordinates world-restore flows for all four selection scopes.

    Construction takes explicit dependencies for testability; the app
    lifespan wires a singleton from real managers.
    """

    def __init__(
        self,
        *,
        restic_manager: ResticManager,
        docker_mc_manager: DockerMCManager,
        server_operation_lock: ServerOperationLock,
        session_factory: SessionFactory,
    ) -> None:
        self._restic = restic_manager
        self._docker = docker_mc_manager
        self._lock = server_operation_lock
        self._session_factory = session_factory

        self._preview_manager = PreviewSessionManager(
            base_dir=PREVIEW_BASE_DIR,
        )

    async def create_snapshot(
        self,
        server_id: str,
        selection: RestorationSelection,
        user_id: Optional[int],
    ) -> ResticSnapshotWithSummary:
        """Acquire BACKUP lock and snapshot the selection paths.

        Safety snapshots created during a restore call ``_restic.backup``
        directly under the outer RESTORE lock instead.
        """
        paths = await self._resolve_paths_for_selection(server_id, selection)
        if not paths:
            raise SelectionResolutionError(
                f"选择范围没有解析到任何文件路径: {selection.model_dump()}"
            )
        selection_label = _selection_label(selection)
        holder = LockHolder(
            kind=ServerOperationKind.BACKUP,
            started_at=datetime.now(timezone.utc),
            user_id=user_id,
            description=f"世界快照（{selection_label}）",
        )
        async with self._lock.acquire(server_id, holder):
            return await self._restic.backup(paths)

    async def list_eligible_snapshots(
        self, server_id: str, selection: RestorationSelection
    ) -> list[ResticSnapshot]:
        """Snapshots covering every selection path.

        MCC sidecars are excluded from eligibility because restic only
        records paths that existed at backup time; including them would
        filter out most prior safety snapshots.
        """
        paths = await self._resolve_eligibility_paths(server_id, selection)
        if not paths:
            return []
        return await self._restic.find_snapshots_covering(paths)

    async def begin_restore(
        self,
        server_id: str,
        source_snapshot_id: str,
        selection: RestorationSelection,
        user_id: Optional[int],
        is_rollback: bool = False,
    ) -> AsyncGenerator[RestoreEvent, None]:
        """Acquire RESTORE lock, take a safety snapshot, persist a row, and run the scope flow."""
        restoration_id = _new_restoration_id()
        selection_label = _selection_label(selection)
        holder = LockHolder(
            kind=ServerOperationKind.RESTORE,
            started_at=datetime.now(timezone.utc),
            user_id=user_id,
            description=f"世界恢复（{selection_label}{'，回档' if is_rollback else ''}）",
            restoration_id=restoration_id,
        )

        async with self._lock.acquire(server_id, holder):
            await self._ensure_server_stopped(server_id)
            paths = await self._resolve_paths_for_selection(server_id, selection)
            if not paths:
                raise SelectionResolutionError(
                    f"选择范围没有解析到任何文件路径: {selection.model_dump()}"
                )

            yield RestoreEvent(
                event_type="start",
                restoration_id=restoration_id,
                message=f"开始恢复{selection_label}",
            )

            yield RestoreEvent(
                event_type="safety_snapshot",
                restoration_id=restoration_id,
                message="正在创建安全快照",
            )
            safety = await self._restic.backup(paths)
            safety_snapshot_id = safety.id
            yield RestoreEvent(
                event_type="safety_snapshot",
                restoration_id=restoration_id,
                safety_snapshot_id=safety_snapshot_id,
                message=f"安全快照 {safety.short_id}",
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
                message=f"已使 {invalidated} 个地图瓦片缓存失效",
            )

            await self._update_restoration_row(
                restoration_id, RestorationStatus.SUCCEEDED, None
            )
            yield RestoreEvent(
                event_type="complete",
                restoration_id=restoration_id,
                message="恢复完成",
            )

    async def rollback(
        self, restoration_id: str, user_id: Optional[int]
    ) -> AsyncGenerator[RestoreEvent, None]:
        """Re-run ``begin_restore`` using the row's safety snapshot as the source."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Restoration).where(Restoration.id == restoration_id)
                )
            ).scalar_one_or_none()
        if row is None:
            raise RestoreError(f"恢复记录不存在: {restoration_id}")
        if not row.safety_snapshot_id:
            raise RestoreError(
                f"恢复记录 {restoration_id} 没有可用于回档的安全快照"
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

    async def begin_preview(
        self,
        server_id: str,
        source_snapshot_id: str,
        selection: RestorationSelection,
    ) -> AsyncGenerator[PreviewEvent, None]:
        """Stage snapshot MCAs to a session dir, run chunk merge, attach a lazy-render queue.

        Tiles render on first request via a per-session ``ServerRenderQueue``
        that reuses the live world's palette. Missing palette surfaces as an
        ``error`` event prompting the user to initialize the live map first.
        """
        paths = await self._resolve_paths_for_selection(server_id, selection)
        if not paths:
            raise SelectionResolutionError(
                f"选择范围没有解析到任何文件路径: {selection.model_dump()}"
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
                message=f"正在从快照 {source_snapshot_id[:8]} 准备预览",
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
                message="快照 MCA 文件准备完成",
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
                message="预览已就绪",
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
        """Copy live MCAs into ``preview/`` then splice selected chunks from the staged snapshot."""
        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()
        roots = await discover_world_roots(data_path)
        if selection.region_dir_relpath is None:
            raise SelectionResolutionError(
                "区块恢复选择范围需要指定维度路径"
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
                        # Snapshot has the region but live doesn't; seed an
                        # empty MCA so mcmap has a target to splice into.
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
        """Wire a lazy-render ``ServerRenderQueue`` against staged MCAs and the live palette.

        Source dirs: ``preview/`` for chunk-scope (merged copies),
        ``source/`` for region-scope (snapshot regions verbatim). PNGs land
        at ``<session_dir>/tiles/r.<rx>.<rz>.png``.
        """
        if selection.region_dir_relpath is None:
            return

        instance = self._docker.get_instance(server_id)
        data_path = instance.get_data_path()
        cache = ServerMapCache(data_path=data_path)
        if not await aioos.path.exists(cache.palette_json):
            raise RestoreError(
                "无法渲染预览：当前地图调色板尚未初始化；请先打开世界地图页面并运行初始化。"
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
        """Return a preview tile, rendering it lazily on first miss.

        Raises ``PreviewSessionNotFoundError`` for unknown sessions,
        ``FileNotFoundError`` for tiles outside the affected set, and
        ``asyncio.TimeoutError`` when the render exceeds ``timeout``.
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
                f"预览瓦片 ({rx}, {rz}) 不可用：渲染队列尚未挂载"
            )
        if sess.affected_keys is not None and (rx, rz) not in sess.affected_keys:
            raise FileNotFoundError(
                f"预览瓦片 ({rx}, {rz}) 不在本次预览受影响的区域范围内"
            )

        effective_timeout = (
            timeout
            if timeout is not None
            else float(dynamic_config.mcmap.request_timeout_seconds)
        )
        return await asyncio.wait_for(queue.request(rx, rz), timeout=effective_timeout)

    def get_preview_session_dir(self, session_id: str) -> Optional[Path]:
        return self._preview_manager.get_session_dir(session_id)

    def start_janitor(self) -> "asyncio.Task":
        return self._preview_manager.start_janitor()

    async def stop_janitor(self) -> None:
        await self._preview_manager.stop_janitor()

    async def _flow_filesystem_restore(
        self,
        *,
        source_snapshot_id: str,
        paths: list[Path],
        restoration_id: str,
        touched_items: list[str],
    ) -> AsyncGenerator[RestoreEvent, None]:
        """In-place restic restore for world / dimension / regions scopes.

        ``touched_items`` collects absolute paths restic wrote or deleted,
        used by the caller for PNG invalidation.
        """
        yield RestoreEvent(
            event_type="restore",
            restoration_id=restoration_id,
            message=f"正在从快照 {source_snapshot_id[:8]} 恢复 {len(paths)} 个路径",
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
                "区块恢复选择范围需要指定维度路径"
            )
        dim = _find_dimension(data_path, roots, selection.region_dir_relpath)

        grouped = _group_chunks_by_region(selection.chunks)
        live_subdirs: dict[str, Optional[Path]] = {
            "region": dim.region_dir,
            "entities": dim.entities_dir,
            "poi": dim.poi_dir,
        }

        include_paths: list[Path] = []
        for (rx, rz) in grouped:
            for sub in SUBDIR_KINDS:
                live_dir = live_subdirs.get(sub)
                if live_dir is None:
                    continue
                include_paths.append(live_dir / f"r.{rx}.{rz}.mca")
                # MCC sidecars (1024 per region) are speculative; restic ignores nonexistent ones.
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
                message=f"正在从快照 {source_snapshot_id[:8]} 准备 {len(grouped)} 个区域",
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
        event_adapter: Any,
        expected_count: int,
    ) -> None:
        async with ctx_manager as proc:
            completed_count: Optional[int] = None
            async for event in proc.events(event_adapter):
                if isinstance(event, MCMapErrorEvent):
                    raise MCMapError(event.message or f"mcmap {op_name} 操作失败")
                if isinstance(event, MCMapReplaceChunksResultEvent):
                    completed_count = event.replaced
                elif isinstance(event, MCMapRemoveChunksResultEvent):
                    completed_count = event.removed
        if proc.returncode != 0:
            raise MCMapError(f"mcmap {op_name} 退出码为 {proc.returncode}")
        if completed_count != expected_count:
            raise MCMapError(
                f"mcmap {op_name} 处理了 {completed_count} 个区块，但请求了 {expected_count} 个区块"
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
            event_adapter=MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER,
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
            event_adapter=MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER,
            expected_count=len(chunks),
        )

    async def _invalidate_map_cache(
        self,
        *,
        server_id: str,
        selection: RestorationSelection,
        touched_items: list[str],
    ) -> int:
        """Drop cached PNG tiles whose source MCA changed.

        WORLD/DIMENSION derives affected regions from ``touched_items``
        (restic verbose_status); REGIONS/CHUNKS uses the selection directly
        as the source of truth.
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
                f"{_selection_label(selection)}选择范围需要指定维度路径"
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

        raise SelectionResolutionError(f"不支持的选择范围类型: {selection.type}")

    async def _resolve_paths_for_selection(
        self, server_id: str, selection: RestorationSelection
    ) -> list[Path]:
        return await self._resolve_paths_core(server_id, selection, include_mcc=True)

    async def _resolve_eligibility_paths(
        self, server_id: str, selection: RestorationSelection
    ) -> list[Path]:
        """MCA-only path resolution; speculative MCC sidecars excluded for eligibility checks."""
        return await self._resolve_paths_core(server_id, selection, include_mcc=False)

    async def _ensure_server_stopped(self, server_id: str) -> None:
        instance = self._docker.get_instance(server_id)
        status = await instance.get_status()
        if status in (
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ):
            raise ServerNotStoppedError(
                f"服务器 '{server_id}' 必须先停止才能恢复世界（当前状态: {status.value}）"
            )

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
        f"未找到维度路径 '{region_dir_relpath}'"
    )


def _expand_region_paths(
    dim: DimensionInfo, regions: list[tuple[int, int]]
) -> list[Path]:
    """Include-path list (MCA + speculative MCCs) for regions/chunks restores."""
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
    """MCA-only variant; speculative MCC sidecars would over-filter eligibility checks."""
    paths: list[Path] = []
    for (rx, rz) in regions:
        for live_dir in (dim.region_dir, dim.entities_dir, dim.poi_dir):
            if live_dir is None:
                continue
            paths.append(live_dir / f"r.{rx}.{rz}.mca")
    return paths


def _count_affected_regions(selection: RestorationSelection) -> int:
    """Disk-guard heuristic used by ``PreviewSessionManager``."""
    if selection.type is RestorationType.REGIONS:
        return len(selection.regions)
    if selection.type is RestorationType.CHUNKS:
        return len({(c[0] // CHUNKS_PER_REGION_AXIS, c[1] // CHUNKS_PER_REGION_AXIS) for c in selection.chunks})
    # WORLD/DIMENSION counts require a disk scan; use a conservative default to avoid false trips.
    return 16
