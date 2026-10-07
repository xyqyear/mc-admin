import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path

import aiofiles
import aiofiles.os as aioos

from app.snapshots.restoration_models import RestorationType
from app.snapshots.selection_models import RestorationSelection

from ..background_tasks import TaskProgress
from ..dynamic_config import get_config as get_dynamic_config
from ..mcmap.cache import ServerMapCache
from ..mcmap.ownership import PreviewRenderTarget
from ..mcmap.queue import ServerRenderQueue
from ..snapshots import SnapshotService
from ..snapshots.preview_sessions import (
    PreviewSessionManager,
    PreviewSessionNotFoundError,
)
from ..snapshots.protection import SnapshotProtection
from ..utils import async_fs
from .events import RestoreError, SelectionResolutionError
from .layout import discover_world_roots
from .scope_execution import (
    RestoreScopeExecutor,
    _stage_destination,
    organize_staged_region,
)
from .selection import (
    _find_dimension,
    _restore_dimension,
    group_chunks_by_region,
    resolve_paths,
)


@dataclass
class PreviewMapCache:
    """Preview paths with the live world's palette and ownership source."""

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


class WorldPreviewRenderer:
    def __init__(
        self,
        snapshots: SnapshotService,
        executor: RestoreScopeExecutor,
        manager: PreviewSessionManager,
    ) -> None:
        self._snapshots = snapshots
        self._executor = executor
        self._preview_manager = manager

    async def prepare(
        self,
        *,
        session_id: str,
        data_path: Path,
        source_snapshot_id: str,
        selection: RestorationSelection,
        paths: tuple[Path, ...],
        protection: SnapshotProtection,
    ) -> AsyncGenerator[TaskProgress]:
        session_dir = self._preview_manager.get_session_dir(session_id)
        if session_dir is None:
            raise PreviewSessionNotFoundError(session_id)
        await aioos.makedirs(session_dir / "source", exist_ok=True)
        yield TaskProgress(message="正在提取快照中的地图数据")
        async with aclosing(
            self._snapshots.stage(
                source_snapshot_id,
                paths,
                session_dir / "source",
                protection=protection,
            )
        ) as events:
            async for event in events:
                if event.kind == "status":
                    yield TaskProgress(
                        message="正在提取快照中的地图数据",
                        progress=event.percent_done * 100
                        if event.percent_done is not None
                        else None,
                    )
        if selection.type in (RestorationType.REGIONS, RestorationType.CHUNKS):
            for path in paths:
                if path.suffix != ".mca":
                    continue
                _, rx, rz, _ = path.name.split(".")
                await organize_staged_region(
                    session_dir / "source", data_path, path, int(rx), int(rz), protection
                )
        if selection.type is RestorationType.REGIONS:
            for path in await resolve_paths(data_path, selection, include_mcc=True):
                if protection.permits(path) or not await aioos.path.isfile(path):
                    continue
                source = await async_fs.resolve_inside(data_path, path)
                destination = await _stage_destination(
                    session_dir / "source", path
                )
                await aioos.makedirs(destination.parent, exist_ok=True)
                await async_fs.copy2(source, destination)
        if selection.type is RestorationType.CHUNKS:
            async for event in self._preview_chunk_merge(
                data_path=data_path,
                selection=selection,
                session_dir=session_dir,
                protection=protection,
            ):
                yield event
        if selection.type in (RestorationType.REGIONS, RestorationType.CHUNKS):
            await self._attach_preview_render_queue(
                data_path=data_path,
                selection=selection,
                session_dir=session_dir,
                session_id=session_id,
            )

    async def _preview_chunk_merge(
        self,
        *,
        data_path: Path,
        selection: RestorationSelection,
        session_dir: Path,
        protection: SnapshotProtection,
    ) -> AsyncGenerator[TaskProgress]:
        """Copy live MCAs into ``preview/`` then splice selected chunks from the staged snapshot."""
        roots = await discover_world_roots(data_path)
        if selection.region_dir_relpath is None:
            raise SelectionResolutionError("区块恢复选择范围需要指定维度路径")
        dim = _restore_dimension(
            _find_dimension(data_path, roots, selection.region_dir_relpath)
        )

        grouped = group_chunks_by_region(selection.chunks)
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
                    for sidecar in await async_fs.iterdir(live_dir):
                        if sidecar.suffix != ".mcc":
                            continue
                        parts = sidecar.name.split(".")
                        if len(parts) != 4 or parts[0] != "c":
                            continue
                        try:
                            in_region = (
                                int(parts[1]) // 32 == rx and int(parts[2]) // 32 == rz
                            )
                        except ValueError:
                            continue
                        if in_region and await aioos.path.isfile(sidecar):
                            confined = await async_fs.resolve_inside(data_path, sidecar)
                            await async_fs.copy2(
                                confined, preview_subdir / sidecar.name
                            )
                allowed = await self._executor.allowed_chunks(
                    data_path, live_mca, rx, rz, local_chunks, protection
                )
                if not allowed:
                    done += 1
                    continue
                if await aioos.path.exists(staged_mca):
                    if not await aioos.path.exists(preview_mca):
                        # Snapshot has the region but live doesn't; seed an
                        # empty MCA so mcmap has a target to splice into.
                        async with aiofiles.open(preview_mca, "wb") as f:
                            await f.write(b"\x00" * 8192)
                    await self._executor.replace_selected_chunks(
                        source_mca=staged_mca,
                        target_mca=preview_mca,
                        chunks=allowed,
                        owned_by=data_path,
                    )
                elif await aioos.path.exists(preview_mca):
                    await self._executor.remove_selected_chunks(
                        target_mca=preview_mca,
                        chunks=allowed,
                        owned_by=data_path,
                    )
                done += 1
                yield TaskProgress(
                    message="正在合并所选区块的预览副本",
                    progress=(done / total) * 100.0 if total else 100.0,
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
            grouped = group_chunks_by_region(selection.chunks)
            affected_iter = list(grouped.keys())
        else:
            source_root = session_dir / "source"
            affected_iter = list(set(selection.regions))

        staged_region_dir = await _stage_destination(source_root, live_region_dir)
        affected_keys: set[tuple[int, int]] = set()
        for rx, rz in affected_iter:
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
        if (
            session is None
            or session.server_generation is None
            or session.server_id is None
        ):
            raise PreviewSessionNotFoundError(session_id)
        queue = ServerRenderQueue(
            server_name=session.server_id,
            region_path=selection.region_dir_relpath,
            cache=preview_cache,
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
            return await asyncio.wait_for(
                queue.request(rx, rz), timeout=effective_timeout
            )
