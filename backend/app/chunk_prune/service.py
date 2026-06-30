from __future__ import annotations

import hashlib
import json
import os
import posixpath
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import aiofiles
import aiofiles.os as aioos

from ..background_tasks import task_manager
from ..background_tasks.types import TaskProgress, TaskStatus, TaskType
from ..ftb_claims.extract import NoFtbDataError, _run_extract
from ..logger import logger
from ..mcmap import runner as mcmap_runner
from ..mcmap.events import (
    MCMAP_PRUNE_EVENT_ADAPTER,
    MCMapChunksPrunedEvent,
    MCMapErrorEvent,
    MCMapPruneProgressEvent,
    MCMapPruneRegionDirEvent,
    MCMapPruneResultEvent,
    MCMapRegionPrunedEvent,
)
from ..minecraft import DockerMCManager, MCServerStatus, docker_mc_manager
from ..world import png_invalidate
from ..world.layout import discover_world_root_paths
from ..world.locks import (
    LockHolder,
    ServerOperationKind,
    ServerOperationLock,
    server_operation_lock,
)
from ..world.region_files import parse_region_filename
from .models import (
    ChunkPrunePreviewRequest,
    ChunkPruneTaskMetadata,
)

TICKS_PER_SECOND = 20
PRUNE_TEMP_BASE_DIR = Path(tempfile.gettempdir()) / "mc-admin-chunk-prune"
STOPPED_STATUSES = {
    MCServerStatus.EXISTS,
    MCServerStatus.CREATED,
    MCServerStatus.REMOVED,
}


class ChunkPruneError(Exception):
    pass


class ChunkPruneTaskNotFound(ChunkPruneError):
    pass


class ChunkPruneValidationError(ChunkPruneError):
    pass


class ChunkPruneConflictError(ChunkPruneError):
    pass


class ChunkPruneService:
    def __init__(
        self,
        *,
        docker: DockerMCManager,
        operation_lock: ServerOperationLock,
    ) -> None:
        self._docker = docker
        self._operation_lock = operation_lock
        self._metadata: dict[str, ChunkPruneTaskMetadata] = {}

    async def start_preview(
        self,
        *,
        server_id: str,
        request: ChunkPrunePreviewRequest,
        user_id: Optional[int] = None,
    ) -> str:
        await self._ensure_server_exists(server_id)
        data_path = self._docker.get_instance(server_id).get_data_path()
        threshold_ticks = seconds_to_ticks(request.threshold_seconds)
        task_id = self._new_task_id("preview", server_id)
        metadata = ChunkPruneTaskMetadata(
            task_id=task_id,
            server_id=server_id,
            operation="preview",
            data_path=data_path,
            threshold_seconds=request.threshold_seconds,
            threshold_ticks=threshold_ticks,
            mode=request.mode,
            user_id=user_id,
        )
        self._metadata[task_id] = metadata

        task_manager.submit(
            TaskType.CHUNK_PRUNE_PREVIEW,
            f"区块清理预览 {server_id}",
            self._run_preview_task(metadata),
            server_id=server_id,
            cancellable=True,
            task_id=task_id,
        )
        return task_id

    async def start_apply(self, *, server_id: str, preview_task_id: str) -> str:
        await self._ensure_server_exists(server_id)
        preview = self._metadata.get(preview_task_id)
        if preview is None or preview.operation != "preview":
            raise ChunkPruneTaskNotFound("Preview task not found")
        if preview.server_id != server_id:
            raise ChunkPruneTaskNotFound("Preview task not found")
        task = task_manager.get_task(preview_task_id)
        if task is None or task.status != TaskStatus.COMPLETED:
            raise ChunkPruneValidationError("Preview task has not completed")
        if preview.result is None:
            raise ChunkPruneValidationError("Preview task has no result")

        status = await self._docker.get_instance(server_id).get_status()
        if status not in STOPPED_STATUSES:
            raise ChunkPruneConflictError("Stop the server before deleting chunks")
        if self._operation_lock.is_locked(server_id):
            raise ChunkPruneConflictError("Another world operation is running")

        task_id = self._new_task_id("apply", server_id)
        metadata = ChunkPruneTaskMetadata(
            task_id=task_id,
            server_id=server_id,
            operation="apply",
            data_path=preview.data_path,
            threshold_seconds=preview.threshold_seconds,
            threshold_ticks=preview.threshold_ticks,
            mode=preview.mode,
            user_id=preview.user_id,
            claims_file=preview.claims_file,
        )
        self._metadata[task_id] = metadata

        task_manager.submit(
            TaskType.CHUNK_PRUNE_APPLY,
            f"区块清理删除 {server_id}",
            self._run_apply_task(metadata),
            server_id=server_id,
            cancellable=True,
            task_id=task_id,
        )
        return task_id

    async def _run_apply_task(
        self, metadata: ChunkPruneTaskMetadata
    ) -> AsyncGenerator[TaskProgress, None]:
        holder = LockHolder(
            kind=ServerOperationKind.PRUNE,
            started_at=datetime.now(timezone.utc),
            user_id=metadata.user_id,
            description="区块清理",
        )
        async with self._operation_lock.acquire(metadata.server_id, holder):
            status = await self._docker.get_instance(metadata.server_id).get_status()
            if status not in STOPPED_STATUSES:
                raise ChunkPruneConflictError("Stop the server before deleting chunks")
            async for progress in self._run_prune_task(metadata, dry_run=False):
                yield progress

            pngs: set[Path] = set()
            for (
                region_dir_relpath,
                regions,
            ) in metadata.affected_regions_by_dimension.items():
                pngs.update(
                    png_invalidate.pngs_for_regions(
                        metadata.data_path,
                        region_dir_relpath,
                        regions,
                    )
                )
            await png_invalidate.delete_pngs(pngs)

    async def _run_prune_task(
        self, metadata: ChunkPruneTaskMetadata, *, dry_run: bool
    ) -> AsyncGenerator[TaskProgress, None]:
        dimensions: dict[str, dict[str, Any]] = {}
        path_mapper = PruneEventPathMapper(metadata.data_path)
        progress_percent = 0.0
        saw_result = False

        if metadata.claims_file is None and metadata.operation == "preview":
            metadata.claims_file = await self._write_claims_file(
                metadata.server_id,
                metadata.data_path,
            )

        async with mcmap_runner.prune_inhabited(
            path=metadata.data_path,
            threshold_ticks=metadata.threshold_ticks,
            mode=metadata.mode,
            dry_run=dry_run,
            owned_by=metadata.data_path,
            exclude_ftb_claims=metadata.claims_file,
        ) as proc:
            async for event in proc.events(MCMAP_PRUNE_EVENT_ADAPTER):
                task = task_manager.get_task(metadata.task_id)
                if task is not None and task.cancel_requested:
                    await proc.terminate()
                    yield TaskProgress(progress=progress_percent, message="已取消")
                    return

                if isinstance(event, MCMapPruneRegionDirEvent):
                    yield TaskProgress(
                        progress=progress_percent,
                        message=f"发现 {event.regions} 个区域文件",
                    )
                elif isinstance(event, MCMapPruneProgressEvent):
                    if event.regions_total > 0:
                        progress_percent = (
                            event.regions_processed / event.regions_total * 100
                        )
                    yield TaskProgress(
                        progress=progress_percent,
                        message=(
                            f"已处理 {event.regions_processed}/"
                            f"{event.regions_total} 个区域文件"
                        ),
                    )
                elif isinstance(event, MCMapChunksPrunedEvent):
                    relpath = path_mapper.region_relpath(event.region)
                    if relpath is None:
                        logger.warning(
                            "chunk-prune: ignored chunks event outside region dir: %s",
                            event.region,
                        )
                        continue
                    self._add_affected_region(
                        metadata, relpath, event.region_x, event.region_z
                    )
                    if dry_run:
                        bucket = dimension_result_bucket(dimensions, relpath)
                        bucket["selected_chunks"].extend(
                            {
                                "chunk_x": chunk.chunk_x,
                                "chunk_z": chunk.chunk_z,
                                "region_x": event.region_x,
                                "region_z": event.region_z,
                            }
                            for chunk in event.chunks
                        )
                elif isinstance(event, MCMapRegionPrunedEvent):
                    relpath = path_mapper.region_relpath(event.region)
                    if relpath is None:
                        logger.warning(
                            "chunk-prune: ignored region event outside region dir: %s",
                            event.region,
                        )
                        continue
                    self._add_affected_region(
                        metadata, relpath, event.region_x, event.region_z
                    )
                    if dry_run:
                        bucket = dimension_result_bucket(dimensions, relpath)
                        bucket["selected_regions"].append(
                            {
                                "region_x": event.region_x,
                                "region_z": event.region_z,
                            }
                        )
                elif isinstance(event, MCMapPruneResultEvent):
                    saw_result = True
                    result = event.model_dump(exclude_none=True)
                    result["threshold_seconds"] = metadata.threshold_seconds
                    result["threshold_ticks"] = metadata.threshold_ticks
                    result["affected_regions_by_dimension"] = {
                        relpath: sorted(regions)
                        for relpath, regions in sorted(
                            metadata.affected_regions_by_dimension.items()
                        )
                    }
                    if dry_run:
                        result["dimensions"] = sorted(
                            dimensions.values(),
                            key=lambda d: d["region_dir_relpath"],
                        )
                    metadata.result = result
                    yield TaskProgress(
                        progress=100,
                        message="清理预览完成" if dry_run else "区块清理完成",
                        result=result,
                    )
                elif isinstance(event, MCMapErrorEvent):
                    raise ChunkPruneError(event.message)

            if proc.returncode not in (0, None):
                stderr = (await proc.stderr()).strip()
                raise ChunkPruneError(stderr or "mcmap prune-inhabited failed")
        if not saw_result:
            raise ChunkPruneError("mcmap prune-inhabited produced no result")

    async def _run_preview_task(
        self, metadata: ChunkPruneTaskMetadata
    ) -> AsyncGenerator[TaskProgress, None]:
        yield TaskProgress(progress=0, message="正在准备预览任务")
        async for progress in self._run_prune_task(metadata, dry_run=True):
            yield progress

    async def _ensure_server_exists(self, server_id: str) -> None:
        instance = self._docker.get_instance(server_id)
        if not await instance.exists():
            raise ChunkPruneTaskNotFound(f"Server '{server_id}' not found")

    async def _write_claims_file(
        self, server_id: str, data_path: Path
    ) -> Optional[Path]:
        world_root = await self._primary_world_root(data_path)
        if world_root is None:
            return None
        try:
            payload = await _run_extract(world_root, data_path)
        except NoFtbDataError:
            return None
        except Exception:
            logger.exception(
                "chunk-prune: failed to extract FTB claims for %s", server_id
            )
            raise ChunkPruneError("Failed to extract FTB claims")

        task_dir = PRUNE_TEMP_BASE_DIR / server_id
        await aioos.makedirs(task_dir, exist_ok=True)
        target = (
            task_dir
            / f"claims-{hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:12]}.json"
        )
        async with aiofiles.open(target, "w") as f:
            await f.write(
                json.dumps(payload.model_dump(mode="json"), separators=(",", ":"))
            )
        return target

    async def _primary_world_root(self, data_path: Path) -> Optional[Path]:
        roots = await discover_world_root_paths(data_path)
        return roots[0].path if roots else None

    def _add_affected_region(
        self,
        metadata: ChunkPruneTaskMetadata,
        region_dir_relpath: str,
        rx: int,
        rz: int,
    ) -> None:
        metadata.affected_regions_by_dimension.setdefault(
            region_dir_relpath, set()
        ).add((rx, rz))

    def _new_task_id(self, operation: str, server_id: str) -> str:
        raw = f"{operation}:{server_id}:{datetime.now(timezone.utc).isoformat()}"
        suffix = hashlib.sha256(raw.encode()).hexdigest()[:24]
        return f"chunk-prune-{operation}-{suffix}"


def seconds_to_ticks(seconds: int) -> int:
    return max(0, int(seconds) * TICKS_PER_SECOND)


def dimension_result_bucket(
    dimensions: dict[str, dict[str, Any]], region_dir_relpath: str
) -> dict[str, Any]:
    bucket = dimensions.get(region_dir_relpath)
    if bucket is None:
        bucket = {
            "region_dir_relpath": region_dir_relpath,
            "selected_chunks": [],
            "selected_regions": [],
        }
        dimensions[region_dir_relpath] = bucket
    return bucket


class PruneEventPathMapper:
    def __init__(self, data_path: Path) -> None:
        self._data_root = normalize_event_path(os.path.abspath(os.fspath(data_path)))

    def region_relpath(self, event_region: str) -> Optional[str]:
        event_path = normalize_event_path(event_region)
        if not event_path or event_path == ".":
            return None

        if event_path.startswith("/"):
            prefix = f"{self._data_root}/"
            if event_path == self._data_root or not event_path.startswith(prefix):
                return None
            relpath = event_path[len(prefix) :]
        else:
            relpath = event_path

        parts = relpath.split("/")
        if (
            len(parts) < 3
            or any(part in ("", ".", "..") for part in parts)
            or parts[-2] != "region"
            or parse_region_filename(parts[-1]) is None
        ):
            return None
        return "/".join(parts[:-1])


def normalize_event_path(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))


def region_relpath_for_event(data_path: Path, event_region: str) -> Optional[str]:
    return PruneEventPathMapper(data_path).region_relpath(event_region)


chunk_prune_service = ChunkPruneService(
    docker=docker_mc_manager,
    operation_lock=server_operation_lock,
)
