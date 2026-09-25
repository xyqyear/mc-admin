import errno
import secrets
from collections.abc import AsyncGenerator
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from typing import Any

import aiofiles
import aiofiles.os as aioos

from app.world.models import RestorationType
from app.world.schemas import RestorationSelection

from ..files.utils import makedirs_with_ownership
from ..mcmap import runner as mcmap_runner
from ..mcmap.events import (
    MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER,
    MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER,
    MCMapErrorEvent,
    MCMapRemoveChunksResultEvent,
    MCMapReplaceChunksResultEvent,
)
from ..mcmap.types import MCMapError
from ..operations.finalization import finalize
from ..snapshots import SnapshotService
from ..utils import async_fs
from .artifacts import restore_stage
from .events import RestoreEvent, SelectionResolutionError
from .selection import (
    SUBDIR_KINDS,
    _group_chunks_by_region,
    _mcc_paths_for_region,
    confined_history_path,
    resolve_dimension,
    selection_directories,
)


async def _stage_destination(stage_dir: Path, live_path: Path) -> Path:
    """Where ``live_path`` will land under ``stage_dir`` after a staged restore."""
    return SnapshotService.stage_destination(
        stage_dir, await async_fs.resolve(live_path)
    )


class RestoreScopeExecutor:
    def __init__(self, snapshots: SnapshotService) -> None:
        self._snapshots = snapshots

    async def _flow_filesystem_restore(
        self,
        *,
        source_snapshot_id: str,
        paths: list[Path],
        restoration_id: str,
        touched_items: list[str],
    ) -> AsyncGenerator[RestoreEvent]:
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
        async with aclosing(self._snapshots.restore(source_snapshot_id, paths)) as events:
            async for ev in events:
                if ev.kind == "status" and ev.percent_done is not None:
                    yield RestoreEvent(
                        event_type="restore",
                        restoration_id=restoration_id,
                        percent=ev.percent_done * 100.0,
                    )
                elif (
                    ev.kind == "file"
                    and ev.action in ("updated", "restored", "deleted")
                    and ev.item is not None
                ):
                    touched_items.append(ev.item)

    async def _flow_chunks(
        self,
        *,
        data_path: Path,
        source_snapshot_id: str,
        selection: RestorationSelection,
        restoration_id: str,
        allow_missing_dimension: bool = False,
    ) -> AsyncGenerator[RestoreEvent]:
        """Stage source MCAs to a temp dir, then merge selected chunks per region."""
        if not selection.chunks:
            return
        if selection.region_dir_relpath is None:
            raise SelectionResolutionError(
                "区块恢复选择范围需要指定维度路径"
            )
        dim = await resolve_dimension(data_path, selection.region_dir_relpath, allow_missing=allow_missing_dimension)
        from .selection import _restore_dimension

        dim = _restore_dimension(dim)

        grouped = _group_chunks_by_region(selection.chunks)
        live_subdirs: dict[str, Path | None] = {
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

        async with restore_stage() as stage_root:
            yield RestoreEvent(
                event_type="stage",
                restoration_id=restoration_id,
                message=f"正在从快照 {source_snapshot_id[:8]} 准备 {len(grouped)} 个区域",
                percent=0.0,
            )
            async with aclosing(self._snapshots.stage(
                source_snapshot_id, include_paths, stage_root
            )) as events:
                async for ev in events:
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
            completed_count: int | None = None
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
        await makedirs_with_ownership(target_mca.parent, owned_by)
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

    async def _restore_absent_sidecars(
        self, data_path: Path, snapshot_id: str, selection: RestorationSelection, absent_dirs: list[str], paths: list[Path],
    ) -> None:
        directories = [await confined_history_path(data_path, relative) for relative in absent_dirs]
        scopes = selection_directories(paths, selection)
        if any(not any(scope.is_relative_to(directory) for scope in scopes) for directory in directories):
            raise SelectionResolutionError("恢复记录中的缺失目录不属于所选范围")
        removed: set[Path] = set()
        for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
            selected = [path for path in paths if path.is_relative_to(directory)]
            selected = [path for path in selected if path not in removed]
            removed.update(selected)
            if selection.type is RestorationType.CHUNKS:
                for path in selected:
                    if path.suffix != ".mca" or not await aioos.path.isfile(path):
                        continue
                    async with aiofiles.open(path, "rb") as file:
                        locations = await file.read(4096)
                    if locations == bytes(4096):
                        await aioos.remove(path)
            else:
                await self._snapshots.remove_absent_paths(snapshot_id, selected)
            try:
                await aioos.rmdir(directory)
            except OSError as exc:
                if exc.errno not in (errno.ENOENT, errno.ENOTEMPTY):
                    raise


@asynccontextmanager
async def safety_backup_paths(
    data_path: Path, paths: list[Path], selection: RestorationSelection, absent_dirs: list[str],
) -> AsyncGenerator[list[Path]]:
    directories = selection_directories(paths, selection)
    created = [await confined_history_path(data_path, relative) for relative in absent_dirs]
    markers: list[Path] = []
    selected: list[Path] = []
    try:
        for directory in directories:
            await finalize(makedirs_with_ownership(directory, data_path))
            if selection.type in (RestorationType.WORLD, RestorationType.DIMENSION):
                selected.append(directory)
                continue
            existing = [path for path in paths if path.parent == directory and await aioos.path.exists(path)]
            selected.extend(existing)
            if not existing:
                marker = directory / f".mc-admin-absence-{secrets.token_hex(16)}"
                markers.append(marker)
                await finalize(makedirs_with_ownership(marker, data_path))
                selected.append(marker)
        yield selected
    finally:
        async def cleanup() -> None:
            for directory in [*markers, *sorted(created, key=lambda path: len(path.parts), reverse=True)]:
                try:
                    await aioos.rmdir(directory)
                except OSError as exc:
                    if exc.errno not in (errno.ENOENT, errno.ENOTEMPTY):
                        raise
        await finalize(cleanup())
