from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, aclosing
from pathlib import Path
from typing import TypeVar

import aiofiles.os as aioos
from pydantic import TypeAdapter

from app.snapshots.selection_models import RestorationSelection

from ..background_tasks import TaskProgress
from ..files.utils import makedirs_with_ownership
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


async def _stage_destination(stage_dir: Path, live_path: Path) -> Path:
    """Where ``live_path`` will land under ``stage_dir`` after a staged restore."""
    return SnapshotService.stage_destination(
        stage_dir, await async_fs.resolve(live_path)
    )


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
        include_paths = [path for path in include_paths if protection.permits(path)]
        protection.require_targets(include_paths)

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
                    staged_mca = await _stage_destination(stage_root, live_mca)
                    if await aioos.path.exists(staged_mca):
                        await self.replace_selected_chunks(
                            source_mca=staged_mca,
                            target_mca=live_mca,
                            chunks=allowed,
                            owned_by=data_path,
                        )
                    else:
                        if not await aioos.path.exists(live_mca):
                            done += 1
                            continue
                        await self.remove_selected_chunks(
                            target_mca=live_mca,
                            chunks=allowed,
                            owned_by=data_path,
                        )
                    done += 1
                    yield TaskProgress(
                        message=f"正在合并 {sub} 区域 ({rx}, {rz})",
                        progress=(done / total_jobs) * 100.0 if total_jobs else 100.0,
                    )

    @staticmethod
    async def allowed_chunks(
        data_path: Path,
        mca: Path,
        rx: int,
        rz: int,
        chunks: list[tuple[int, int]],
        protection: SnapshotProtection,
    ) -> list[tuple[int, int]]:
        if not protection.permits(mca) or not protection.permits(
            await async_fs.resolve_inside(data_path, mca)
        ):
            return []
        allowed = []
        for x, z in chunks:
            sidecar = mca.parent / f"c.{rx * 32 + x}.{rz * 32 + z}.mcc"
            canonical = await async_fs.resolve_inside(data_path, sidecar)
            # An external chunk's MCA entry and MCC payload form one writable unit.
            if protection.permits(sidecar) and protection.permits(canonical):
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
