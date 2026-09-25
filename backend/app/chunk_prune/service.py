from __future__ import annotations

import json
import secrets
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import aiofiles.os as aioos

from ..background_tasks import get_task_manager
from ..background_tasks.types import TaskProgress, TaskStatus, TaskType
from ..config import get_settings
from ..db.database import get_async_session
from ..errors import PublicOperationError, log_safe_error
from ..ftb_claims.extract import NoFtbDataError, extract_claims_payload
from ..minecraft import DockerMCManager, MCServerStatus
from ..operations.context import mark_cache_degraded, record_phase
from ..operations.coordinator import ResourceClaim, ResourceKind
from ..operations.execution import settle_before_release
from ..operations.finalization import finalize
from ..runtime_resources import current_runtime
from ..servers.references import ServerRef, resolve_server_ref
from ..utils import async_fs
from ..world import png_invalidate
from ..world.artifacts import artifact_root, release_artifact, retain_artifact
from ..world.layout import discover_world_root_paths
from ..world.locks import (
    LockHolder,
    ServerOperationKind,
    ServerOperationLock,
)
from .execution import ChunkPruneError, run_prune
from .geometry import region_relpath_for_event
from .inputs import (
    PruneInputVersion,
    PrunePreviewConflict,
    payload_digest,
    require_supported_adapter,
    world_manifest,
)
from .lifecycle import PrunePreviewRegistry
from .models import (
    ChunkPrunePreviewGeometryResponse,
    ChunkPrunePreviewRequest,
    ChunkPruneTaskMetadata,
)

__all__ = [
    "ChunkPruneConflictError",
    "ChunkPruneError",
    "ChunkPruneService",
    "ChunkPruneTaskNotFound",
    "ChunkPruneValidationError",
    'get_chunk_prune_service',
    "region_relpath_for_event",
    "seconds_to_ticks",
]

TICKS_PER_SECOND = 20
STOPPED_STATUSES = {MCServerStatus.EXISTS, MCServerStatus.CREATED, MCServerStatus.REMOVED}


class ChunkPruneTaskNotFound(ChunkPruneError, PublicOperationError):
    pass


class ChunkPruneValidationError(ChunkPruneError, PublicOperationError):
    pass


class ChunkPruneConflictError(ChunkPruneError, PublicOperationError):
    pass


class ChunkPruneService:
    def __init__(self, *, docker: DockerMCManager, operation_lock: ServerOperationLock,
                 temp_base_dir: Path | None = None) -> None:
        self._docker = docker
        self._operation_lock = operation_lock
        self.registry = PrunePreviewRegistry(temp_base_dir if temp_base_dir is not None else artifact_root("prune"))
        self._metadata = self.registry.metadata
        self._temp_base_dir = self.registry.base_dir

    async def start(self) -> None:
        await self.registry.start()

    async def close(self, *, preserve_artifacts: bool = False) -> None:
        await self.registry.close(preserve_artifacts=preserve_artifacts)

    async def _reference(self, server_id: str) -> ServerRef:
        settings = get_settings()
        async with get_async_session() as session:
            return await resolve_server_ref(session, server_id, servers_root=settings.server_path)

    @staticmethod
    def _claims(reference: ServerRef) -> list[ResourceClaim]:
        return [ResourceClaim(ResourceKind.FILES, reference.server_id, reference.data_path.relative_to(reference.project_path).as_posix()),
                ResourceClaim(ResourceKind.MAP_CACHE, reference.server_id)]

    async def start_preview(self, *, server_id: str, request: ChunkPrunePreviewRequest,
                            user_id: int | None = None) -> str:
        reference = await self._reference(server_id)
        await self.registry.reserve_capacity()
        task_id = self._new_task_id("preview")
        metadata = ChunkPruneTaskMetadata(
            task_id=task_id, server_id=server_id, operation="preview", reference=reference,
            data_path=reference.data_path, threshold_seconds=request.threshold_seconds,
            threshold_ticks=seconds_to_ticks(request.threshold_seconds), mode=request.mode,
            user_id=user_id, created_at=self.registry.now(),
        )
        self._metadata[task_id] = metadata
        try:
            submitted = await get_task_manager().submit_durable(
                TaskType.CHUNK_PRUNE_PREVIEW, f"区块清理预览 {server_id}", self._run_preview_task(metadata),
                server_id=server_id, cancellable=True, task_id=task_id, actor_id=user_id,
                claims=[ResourceClaim(ResourceKind.MAP_CACHE, server_id)],
            )
            metadata.task = submitted.task
        except BaseException:
            self._metadata.pop(task_id, None)
            raise
        return task_id

    def _preview(self, server_id: str, task_id: str) -> ChunkPruneTaskMetadata:
        preview = self._metadata.get(task_id)
        if preview is None or preview.operation != "preview" or preview.server_id != server_id:
            raise ChunkPruneTaskNotFound("裁剪预览不存在，请重新预览")
        return preview

    async def start_apply(self, *, server_id: str, preview_task_id: str,
                          user_id: int | None = None) -> str:
        preview = self._preview(server_id, preview_task_id)
        self.registry.require_ready(preview)
        task = self.registry.task(preview)
        if task is None or task.status != TaskStatus.COMPLETED or preview.result is None or preview.inputs is None:
            raise ChunkPruneValidationError("裁剪预览尚未完成或不可用")
        status = await self._docker.get_instance(server_id).get_status()
        if status not in STOPPED_STATUSES:
            raise ChunkPruneConflictError("请先停止服务器再应用裁剪")
        if self._operation_lock.is_locked(server_id):
            raise ChunkPruneConflictError("另一项世界操作正在运行")
        self.registry.require_ready(preview)
        task_id = self._new_task_id("apply")
        preview.apply_task_id = task_id
        preview.references += 1
        try:
            await self._validate_inputs(preview)
            metadata = ChunkPruneTaskMetadata(
                task_id=task_id, server_id=server_id, operation="apply", reference=preview.reference,
                data_path=preview.data_path, threshold_seconds=preview.threshold_seconds,
                threshold_ticks=preview.threshold_ticks, mode=preview.mode, user_id=user_id,
                claims_file=preview.claims_file, inputs=preview.inputs, preview_task_id=preview_task_id,
                created_at=self.registry.now(),
                affected_regions_by_dimension={key: set(value) for key, value in preview.affected_regions_by_dimension.items()},
            )
            self._metadata[task_id] = metadata
            assert metadata.reference is not None
            submitted = await get_task_manager().submit_durable(
                TaskType.CHUNK_PRUNE_APPLY, f"区块清理删除 {server_id}", self._run_apply_task(metadata),
                server_id=server_id, cancellable=True, task_id=task_id, actor_id=metadata.user_id,
                claims=self._claims(metadata.reference),
            )
            metadata.task = submitted.task
            submitted.awaitable.add_done_callback(lambda _: self._release_preview(preview))
        except BaseException:
            preview.apply_task_id = None
            preview.references -= 1
            self._metadata.pop(task_id, None)
            raise
        return task_id

    @staticmethod
    def _release_preview(preview: ChunkPruneTaskMetadata) -> None:
        preview.references -= 1

    def get_preview_geometry(self, *, server_id: str, preview_task_id: str) -> ChunkPrunePreviewGeometryResponse:
        preview = self._preview(server_id, preview_task_id)
        state = self.registry.state(preview).availability
        if state in {"expired", "stale"} and not preview.references:
            raise PrunePreviewConflict(state)
        if preview.geometry is None:
            raise ChunkPruneValidationError("裁剪预览图形不可用，请重新预览")
        return preview.geometry

    async def _read_claims(self, data_path: Path) -> dict | None:
        roots = await discover_world_root_paths(data_path)
        if not roots:
            return None
        try:
            payload = await extract_claims_payload(roots[0].path, data_path)
            return payload.model_dump(mode="json")
        except NoFtbDataError:
            return None
        except Exception as error:
            log_safe_error(error, "chunk prune claims extraction failed")
            raise PublicOperationError("读取领地保护信息失败，请检查领地数据") from error

    async def _capture_inputs(self, metadata: ChunkPruneTaskMetadata) -> tuple[PruneInputVersion, dict | None]:
        reference = await self._reference(metadata.server_id)
        if reference != metadata.reference:
            raise PrunePreviewConflict("stale")
        before = await world_manifest(reference.data_path)
        payload = await self._read_claims(reference.data_path)
        if before != await world_manifest(reference.data_path):
            raise PrunePreviewConflict("stale")
        return PruneInputVersion.capture(reference, metadata.threshold_ticks, metadata.mode, before, payload_digest(payload)), payload

    async def _validate_inputs(self, preview: ChunkPruneTaskMetadata) -> None:
        expires = self.registry.expires_at(preview)
        if expires is not None and self.registry.now() >= expires:
            preview.unavailable_reason = "expired"
            raise PrunePreviewConflict("expired")
        await require_supported_adapter()
        try:
            current, _ = await self._capture_inputs(preview)
            if current != preview.inputs:
                raise PrunePreviewConflict("stale")
            if preview.claims_file is not None:
                async with aiofiles.open(preview.claims_file) as file:
                    if payload_digest(json.loads(await file.read())) != current.claims_digest:
                        raise PrunePreviewConflict("stale")
        except PrunePreviewConflict:
            preview.unavailable_reason = "stale"
            raise
        except (FileNotFoundError, json.JSONDecodeError) as error:
            preview.unavailable_reason = "stale"
            raise PrunePreviewConflict("stale") from error

    async def _run_preview_task(self, metadata: ChunkPruneTaskMetadata) -> AsyncGenerator[TaskProgress]:
        ready = False
        try:
            await retain_artifact("prune_preview", metadata.task_id)
            await require_supported_adapter()
            inputs, payload = await self._capture_inputs(metadata)
            task_dir = self._temp_base_dir / metadata.task_id
            await aioos.makedirs(task_dir, exist_ok=False)
            if payload is not None:
                claims_file = task_dir / "claims.json"
                metadata.claims_file = claims_file
                async def write_claims() -> None:
                    async with aiofiles.open(claims_file, "w") as file:
                        await file.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
                await finalize(write_claims())
            metadata.inputs = inputs
            yield TaskProgress(progress=0, message="正在准备预览任务")
            async with aclosing(run_prune(metadata, dry_run=True)) as events:
                async for progress in events:
                    yield progress
            await self._validate_inputs(metadata)
            metadata.completed_at = self.registry.now()
            ready = True
        finally:
            if not ready:
                metadata.unavailable_reason = "unavailable" if metadata.unavailable_reason is None else metadata.unavailable_reason
                metadata.geometry = None
            await finalize(release_artifact("prune_preview", metadata.task_id))

    async def _run_prune_task(self, metadata: ChunkPruneTaskMetadata, *, dry_run: bool) -> AsyncGenerator[TaskProgress]:
        async with aclosing(run_prune(metadata, dry_run=dry_run)) as events:
            async for progress in events:
                yield progress

    async def _run_apply_task(self, metadata: ChunkPruneTaskMetadata) -> AsyncGenerator[TaskProgress]:
        assert metadata.reference is not None and metadata.preview_task_id is not None
        preview = self._preview(metadata.server_id, metadata.preview_task_id)
        holder = LockHolder(ServerOperationKind.PRUNE, datetime.now(UTC), metadata.user_id, "区块清理")
        async with (
            self._operation_lock.lease([metadata.server_id], holder, claims=self._claims(metadata.reference)),
            settle_before_release(),
        ):
            status = await self._docker.get_instance(metadata.server_id).get_status()
            if status not in STOPPED_STATUSES:
                raise ChunkPruneConflictError("请先停止服务器再应用裁剪")
            await self._validate_inputs(preview)
            await async_fs.resolve_inside(metadata.data_path, metadata.data_path / ".mcmap" / "tiles")
            for path in metadata.affected_regions_by_dimension:
                await async_fs.resolve_inside(metadata.data_path, metadata.data_path / ".mcmap" / "tiles" / path)
            await retain_artifact("prune_preview", preview.task_id)
            try:
                await record_phase("pruning_world", changed=True)
                async with aclosing(run_prune(metadata, dry_run=False)) as events:
                    async for progress in events:
                        yield progress
            finally:
                async def cleanup() -> None:
                    try:
                        pngs = set()
                        for path, regions in metadata.affected_regions_by_dimension.items():
                            pngs.update(png_invalidate.pngs_for_regions(metadata.data_path, path, regions))
                        try:
                            await png_invalidate.delete_pngs(pngs, data_path=metadata.data_path)
                        except Exception:
                            await mark_cache_degraded(metadata.server_id)
                            raise
                    finally:
                        await release_artifact("prune_preview", preview.task_id)
                await finalize(cleanup())

    @staticmethod
    def _new_task_id(operation: str) -> str:
        return f"chunk-prune-{operation}-{secrets.token_hex(12)}"


def seconds_to_ticks(seconds: int) -> int:
    return max(0, int(seconds) * TICKS_PER_SECOND)


def get_chunk_prune_service() -> ChunkPruneService:
    return current_runtime().resource('chunk_prune_service')
