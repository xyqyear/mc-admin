import secrets
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, aclosing
from pathlib import Path
from typing import TypeVar

import aiofiles
import aiofiles.os as aioos
from pydantic import TypeAdapter

from app.snapshots.selection_models import RestorationSelection

from ..background_tasks import TaskProgress
from ..files.utils import makedirs_with_ownership, set_file_ownership
from ..mcmap import runner as mcmap_runner
from ..mcmap.events import (
    MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER,
    MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER,
    MCMapErrorEvent,
    MCMapRemoveChunksEvent,
    MCMapRemoveChunksResultEvent,
    MCMapReplaceChunksEvent,
    MCMapReplaceChunksResultEvent,
)
from ..mcmap.types import MCMapError
from ..operations.finalization import finalize
from ..snapshots import SnapshotService
from ..snapshots.protection import SnapshotProtection
from ..utils import async_fs
from .artifacts import restore_stage
from .events import SelectionResolutionError
from .selection import (
    SUBDIR_KINDS,
    _mcc_paths_for_region,
    group_chunks_by_region,
    resolve_dimension,
)

ChunkEvent = TypeVar("ChunkEvent", MCMapReplaceChunksEvent, MCMapRemoveChunksEvent)


async def _stage_destination(
    stage_dir: Path,
    live_path: Path,
) -> Path:
    """Locate an organized world file or directory beneath staging."""
    path = (
        await async_fs.resolve(live_path.parent) / live_path.name
        if live_path.suffix in {".mca", ".mcc"}
        else await async_fs.resolve(live_path)
    )
    return SnapshotService.stage_destination(stage_dir, path)


async def organize_staged_region(
    stage_dir: Path,
    data_path: Path,
    mca: Path,
    rx: int,
    rz: int,
    protection: SnapshotProtection,
) -> Path:
    directory = await async_fs.resolve_inside(data_path, mca.parent)
    destination = SnapshotService.stage_destination(stage_dir, directory)
    mappings = {item.logical: item.execution for item in protection.mappings}
    for path in [mca, *_mcc_paths_for_region(mca.parent, rx, rz)]:
        if not protection.permits(path):
            continue
        execution = mappings.get(path)
        source = SnapshotService.stage_destination(
            stage_dir,
            execution if execution is not None else protection.execution_path(path),
        )
        target = destination / path.name
        if source != target and await aioos.path.isfile(source):
            await aioos.makedirs(destination, exist_ok=True)
            await async_fs.copy2(source, target)
    return destination / mca.name


async def _publish_chunk_file(
    source: Path, target: Path, data_path: Path,
) -> None:
    if not await aioos.path.isfile(source):
        try:
            await aioos.unlink(target)
        except FileNotFoundError:
            pass
        return
    await makedirs_with_ownership(target.parent, data_path)
    temporary = target.parent / f".mc-admin-chunk-{secrets.token_hex(16)}"
    try:
        async with aiofiles.open(temporary, "xb"):
            pass
        await async_fs.copy2(source, temporary)
        await set_file_ownership(temporary, data_path)
        await aioos.replace(temporary, target)
    finally:
        try:
            await aioos.unlink(temporary)
        except FileNotFoundError:
            pass


class RestoreScopeExecutor:
    def __init__(self, snapshots: SnapshotService) -> None:
        self._snapshots = snapshots

    async def restore_chunks(
        self,
        *,
        data_path: Path,
        source_snapshot_id: str,
        selection: RestorationSelection,
        allow_missing_dimension: bool = False,
        protection: SnapshotProtection,
    ) -> AsyncGenerator[TaskProgress]:
        """Stage source MCAs to a temp dir, then merge selected chunks per region."""
        if not selection.chunks:
            return
        if selection.region_dir_relpath is None:
            raise SelectionResolutionError("区块恢复选择范围需要指定维度路径")
        dim = await resolve_dimension(
            data_path,
            selection.region_dir_relpath,
            allow_missing=allow_missing_dimension,
        )
        from .selection import _restore_dimension

        dim = _restore_dimension(dim)

        grouped = group_chunks_by_region(selection.chunks)
        live_subdirs: dict[str, Path | None] = {
            "region": dim.region_dir,
            "entities": dim.entities_dir,
            "poi": dim.poi_dir,
        }

        include_paths: list[Path] = []
        for rx, rz in grouped:
            for sub in SUBDIR_KINDS:
                live_dir = live_subdirs.get(sub)
                if live_dir is None:
                    continue
                include_paths.append(live_dir / f"r.{rx}.{rz}.mca")
                # MCC sidecars (1024 per region) are speculative; restic ignores nonexistent ones.
                include_paths.extend(_mcc_paths_for_region(live_dir, rx, rz))
        include_paths = list(protection.select_targets(include_paths))

        async with restore_stage() as stage_root:
            yield TaskProgress(
                message=f"正在从快照 {source_snapshot_id[:8]} 准备 {len(grouped)} 个区域",
                progress=0.0,
            )
            async with aclosing(
                self._snapshots.stage(
                    source_snapshot_id, include_paths, stage_root, protection=protection
                )
            ) as events:
                async for ev in events:
                    if ev.kind == "status" and ev.percent_done is not None:
                        yield TaskProgress(
                            progress=ev.percent_done * 100.0,
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
                    allowed = await self.allowed_chunks(
                        data_path, live_mca, rx, rz, local_chunks, protection
                    )
                    if not allowed:
                        done += 1
                        continue
                    staged_mca = await organize_staged_region(
                        stage_root, data_path, live_mca, rx, rz, protection
                    )
                    if not await aioos.path.exists(staged_mca) and not await aioos.path.exists(live_mca):
                        done += 1
                        continue
                    await self._apply_chunks(
                        data_path=data_path,
                        live_mca=live_mca,
                        source_mca=staged_mca,
                        rx=rx,
                        rz=rz,
                        chunks=allowed,
                        protection=protection,
                        work_dir=stage_root / "work" / sub / f"{rx}.{rz}",
                    )
                    done += 1
                    yield TaskProgress(
                        message=f"正在合并 {sub} 区域 ({rx}, {rz})",
                        progress=(done / total_jobs) * 100.0 if total_jobs else 100.0,
                    )

    async def _apply_chunks(
        self,
        *,
        data_path: Path,
        live_mca: Path,
        source_mca: Path,
        rx: int,
        rz: int,
        chunks: list[tuple[int, int]],
        protection: SnapshotProtection,
        work_dir: Path,
    ) -> None:
        directory = await async_fs.resolve_inside(data_path, live_mca.parent)
        sidecars = [
            live_mca.parent / f"c.{rx * 32 + x}.{rz * 32 + z}.mcc"
            for x, z in chunks
        ]
        for path in [live_mca, *sidecars]:
            actual = await async_fs.resolve_inside(data_path, path)
            if actual != protection.execution_path(path):
                raise SelectionResolutionError("世界文件路径已变化，请重新确认操作")
        isolated = any(
            protection.execution_path(path) != directory / path.name
            for path in [live_mca, *sidecars]
        )
        target_mca = protection.execution_path(live_mca)
        if isolated:
            await aioos.makedirs(work_dir, exist_ok=True)
            if await aioos.path.isfile(live_mca):
                await async_fs.copy2(
                    await async_fs.resolve_inside(data_path, live_mca),
                    work_dir / live_mca.name,
                )
            if await aioos.path.isdir(live_mca.parent):
                related = set(_mcc_paths_for_region(live_mca.parent, rx, rz))
                for sidecar in await async_fs.iterdir(live_mca.parent):
                    if sidecar not in related:
                        continue
                    if await aioos.path.isfile(sidecar):
                        await async_fs.copy2(
                            await async_fs.resolve_inside(data_path, sidecar),
                            work_dir / sidecar.name,
                        )
            target_mca = work_dir / live_mca.name
        if await aioos.path.exists(source_mca):
            await self.replace_selected_chunks(
                source_mca=source_mca,
                target_mca=target_mca,
                chunks=chunks,
                owned_by=data_path,
            )
        else:
            await self.remove_selected_chunks(
                target_mca=target_mca,
                chunks=chunks,
                owned_by=data_path,
            )
        if isolated:
            async def publish() -> None:
                targets = []
                for path in [*sidecars, live_mca]:
                    target = await async_fs.resolve_inside(data_path, path)
                    if target != protection.execution_path(path):
                        raise SelectionResolutionError("世界文件路径已变化，请重新确认操作")
                    targets.append((path, target))
                for path, target in targets:
                    if await async_fs.resolve_inside(data_path, path) != target:
                        raise SelectionResolutionError("世界文件路径已变化，请重新确认操作")
                    await _publish_chunk_file(work_dir / path.name, target, data_path)

            await finalize(publish())

    @staticmethod
    async def allowed_chunks(
        data_path: Path,
        mca: Path,
        rx: int,
        rz: int,
        chunks: list[tuple[int, int]],
        protection: SnapshotProtection,
    ) -> list[tuple[int, int]]:
        await async_fs.resolve_inside(data_path, mca)
        if not protection.permits(mca):
            return []
        allowed = []
        for x, z in chunks:
            sidecar = mca.parent / f"c.{rx * 32 + x}.{rz * 32 + z}.mcc"
            await async_fs.resolve_inside(data_path, sidecar)
            # An external chunk's MCA entry and MCC payload form one writable unit.
            if protection.permits(sidecar):
                allowed.append((x, z))
        return allowed

    async def _run_chunk_op(
        self,
        *,
        op_name: str,
        ctx_manager: AbstractAsyncContextManager[mcmap_runner.MCMapProcess],
        event_adapter: TypeAdapter[ChunkEvent],
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

    async def replace_selected_chunks(
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

    async def remove_selected_chunks(
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
