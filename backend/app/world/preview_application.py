import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path

import aiofiles
import aiofiles.os as aioos

from app.world.models import RestorationType
from app.world.schemas import RestorationSelection

from ..dynamic_config import get_config as get_dynamic_config
from ..errors import log_safe_error, public_error_message
from ..mcmap.cache import ServerMapCache
from ..mcmap.ownership import PreviewRenderTarget
from ..mcmap.queue import ServerRenderQueue
from ..operations.context import current_execution
from ..operations.journal_types import OperationState
from ..snapshots import SnapshotService
from ..utils import async_fs
from .artifacts import release_artifact
from .events import PreviewEvent, RestoreError, SelectionResolutionError
from .layout import discover_world_roots
from .preview import (
    PreviewMapCache,
    PreviewSessionManager,
    PreviewSessionNotFoundError,
)
from .scope_execution import RestoreScopeExecutor, _stage_destination
from .selection import (
    _count_affected_regions,
    _find_dimension,
    _group_chunks_by_region,
    _restore_dimension,
    resolve_paths,
)


class WorldPreviewApplication:
    def __init__(self, snapshots: SnapshotService, executor: RestoreScopeExecutor, manager: PreviewSessionManager) -> None:
        self._snapshots = snapshots
        self._executor = executor
        self._preview_manager = manager

    async def begin_preview(
        self,
        server_id: str,
        data_path: Path,
        source_snapshot_id: str,
        selection: RestorationSelection,
        server_generation: int,
    ) -> AsyncGenerator[PreviewEvent]:
        """Stage snapshot MCAs to a session dir, run chunk merge, attach a lazy-render queue.

        Tiles render on first request via a per-session ``ServerRenderQueue``
        that reuses the live world's palette. Missing palette surfaces as an
        ``error`` event prompting the user to initialize the live map first.
        """
        paths = await resolve_paths(data_path, selection, include_mcc=True)
        if not paths:
            raise SelectionResolutionError(
                f"选择范围没有解析到任何文件路径: {selection.model_dump()}"
            )

        affected_regions = _count_affected_regions(selection)
        session_dir = await self._preview_manager.create_session(
            server_id, affected_regions=affected_regions, server_generation=server_generation
        )
        session_id = session_dir.name

        ready = False
        try:
            async with self._preview_manager.use(session_id):
                yield PreviewEvent(
                    event_type="start",
                    session_id=session_id,
                    message=f"正在从快照 {source_snapshot_id[:8]} 准备预览",
                )
                await aioos.makedirs(session_dir / "source", exist_ok=True)
                async with aclosing(self._snapshots.stage(
                    source_snapshot_id, paths, session_dir / "source"
                )) as events:
                    async for _ in events:
                        pass
                yield PreviewEvent(
                    event_type="stage",
                    session_id=session_id,
                    message="快照 MCA 文件准备完成",
                )

                if selection.type is RestorationType.CHUNKS:
                    async for ev in self._preview_chunk_merge(
                        data_path=data_path,
                        selection=selection,
                        session_dir=session_dir,
                        session_id=session_id,
                    ):
                        yield ev

                if selection.type in (RestorationType.REGIONS, RestorationType.CHUNKS):
                    await self._attach_preview_render_queue(
                        data_path=data_path,
                        selection=selection,
                        session_dir=session_dir,
                        session_id=session_id,
                    )

                ready = True
                yield PreviewEvent(
                    event_type="ready",
                    session_id=session_id,
                    message="预览已就绪",
                )
        except Exception as exc:  # noqa: BLE001 - the SSE error boundary excludes adapter exception values
            operation = current_execution()
            if operation is not None:
                operation.outcome = OperationState.FAILED
            log_safe_error(exc, "world preview failed")
            yield PreviewEvent(
                event_type="error",
                session_id=session_id,
                message=public_error_message(exc),
            )
        finally:
            from ..operations.finalization import finalize

            async def cleanup() -> None:
                await release_artifact("world_preview", session_id)
                session = self._preview_manager._sessions.get(session_id)
                if not ready or (session is not None and session.closing):
                    await self._preview_manager.end(session_id)

            await finalize(cleanup())

    async def _preview_chunk_merge(
        self,
        *,
        data_path: Path,
        selection: RestorationSelection,
        session_dir: Path,
        session_id: str,
    ) -> AsyncGenerator[PreviewEvent]:
        """Copy live MCAs into ``preview/`` then splice selected chunks from the staged snapshot."""
        roots = await discover_world_roots(data_path)
        if selection.region_dir_relpath is None:
            raise SelectionResolutionError(
                "区块恢复选择范围需要指定维度路径"
            )
        dim = _restore_dimension(_find_dimension(data_path, roots, selection.region_dir_relpath))

        grouped = _group_chunks_by_region(selection.chunks)
        live_subdirs: dict[str, Path | None] = {
            "region": dim.region_dir,
            "entities": dim.entities_dir,
            "poi": dim.poi_dir,
        }

        preview_dir = session_dir / "preview"
        total = len(grouped) * sum(1 for v in live_subdirs.values() if v is not None)
        done = 0
        for (rx, rz), local_chunks in grouped.items():
            for live_dir in live_subdirs.values():
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
                    await self._executor._merge_replace(
                        source_mca=staged_mca,
                        target_mca=preview_mca,
                        chunks=local_chunks,
                        owned_by=data_path,
                    )
                elif await aioos.path.exists(preview_mca):
                    await self._executor._merge_remove(
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
        data_path: Path,
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
        session = self._preview_manager.get_session(session_id)
        if session is None or session.server_generation is None:
            raise PreviewSessionNotFoundError(session_id)
        queue = ServerRenderQueue(
            server_name=session.server_id,
            region_path=selection.region_dir_relpath,
            cache=preview_cache,  # type: ignore[arg-type]
            preview_target=PreviewRenderTarget(
                server_id=session.server_id,
                generation=session.server_generation,
                session_id=session_id,
                session_dir=session_dir,
            ),
        )
        self._preview_manager.attach_render_queue(
            session_id, queue=queue, affected_keys=affected_keys
        )

    async def read_preview_tile(
        self, session_id: str, rx: int, rz: int, *, timeout: float | None = None
    ) -> bytes:
        async with self._preview_manager.use(session_id):
            path = await self.request_preview_tile(session_id, rx, rz, timeout=timeout)
            async with aiofiles.open(path, "rb") as file:
                return await file.read()

    async def request_preview_tile(
        self, session_id: str, rx: int, rz: int, *, timeout: float | None = None
    ) -> Path:
        """Return a preview tile, rendering it lazily on first miss.

        Raises ``PreviewSessionNotFoundError`` for unknown sessions,
        ``FileNotFoundError`` for tiles outside the affected set, and
        ``asyncio.TimeoutError`` when the render exceeds ``timeout``.
        """
        async with self._preview_manager.use(session_id) as sess:

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
                else float(get_dynamic_config().mcmap.request_timeout_seconds)
            )
            return await asyncio.wait_for(queue.request(rx, rz), timeout=effective_timeout)
