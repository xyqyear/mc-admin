"""Application boundary for owned world restoration and preview flows."""

import asyncio
import json
import secrets
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path

from anyio import CancelScope

from app.world.models import Restoration, RestorationStatus, RestorationType
from app.world.schemas import RestorationSelection

from ..config import get_settings
from ..errors import log_safe_error, public_error_message
from ..files.resources import path_claims, require_same_claims
from ..minecraft import DockerMCManager, MCServerStatus
from ..operations.coordinator import ResourceClaim, ResourceKind
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from ..servers.references import ServerRef, resolve_server_ref, revalidate_server_ref
from ..snapshots import ResticSnapshot, ResticSnapshotWithSummary, SnapshotService
from .artifacts import artifact_root, reap_restore_stages
from .events import (
    PreviewEvent,
    RestoreError,
    RestoreEvent,
    SelectionResolutionError,
    ServerNotStoppedError,
)
from .finalization import invalidate_map_cache
from .locks import LockHolder, ServerOperationKind, ServerOperationLock
from .preview import PreviewSessionManager
from .preview_application import WorldPreviewApplication
from .restoration_store import (
    RestorationStore,
    SessionFactory,
    require_restoration_owner,
)
from .scope_execution import RestoreScopeExecutor, safety_backup_paths
from .selection import (
    _selection_label,
    absent_directories,
    confined_history_path,
    resolve_paths,
    resource_scopes,
)

__all__ = ["PreviewEvent", "RestoreError", "RestoreEvent", "SelectionResolutionError",
           "ServerNotStoppedError", "WorldRestoreOrchestrator"]


class WorldRestoreOrchestrator:
    def __init__(
        self, *, snapshot_service: SnapshotService, docker_mc_manager: DockerMCManager,
        server_operation_lock: ServerOperationLock, session_factory: SessionFactory,
        preview_base_dir: Path | None = None, servers_root: Path | None = None,
    ) -> None:
        settings = get_settings()
        from ..snapshots.application import SnapshotApplication

        self._snapshots = snapshot_service
        self._docker = docker_mc_manager
        self._lock = server_operation_lock
        self._session_factory = session_factory
        self._servers_root = servers_root if servers_root is not None else settings.server_path
        self._store = RestorationStore(session_factory)
        self._backups = SnapshotApplication(snapshot_service, docker_mc_manager, server_operation_lock)
        self._executor = RestoreScopeExecutor(snapshot_service)
        self._preview_manager = PreviewSessionManager(
            preview_base_dir if preview_base_dir is not None else artifact_root("restore"),
        )
        self._previews = WorldPreviewApplication(snapshot_service, self._executor, self._preview_manager)

    async def _reference(self, server_id: str) -> ServerRef:
        async with self._session_factory() as session:
            return await resolve_server_ref(session, server_id, servers_root=self._servers_root)

    async def prepare(self) -> None:
        await self._preview_manager.reap_orphan_dirs()
        await reap_restore_stages()

    async def _revalidate(self, reference: ServerRef) -> None:
        async with self._session_factory() as session:
            await revalidate_server_ref(session, reference)

    async def require_rollback_owner(self, restoration: Restoration) -> None:
        require_restoration_owner(restoration, await self._reference(restoration.server_id))

    @staticmethod
    async def _claims(reference: ServerRef, paths: list[Path]) -> list[ResourceClaim]:
        scopes = await resource_scopes(reference.data_path, paths)
        return list(await path_claims(reference.project_path, scopes, server_id=reference.server_id))

    async def create_snapshot(self, server_id: str, selection: RestorationSelection, user_id: int | None) -> ResticSnapshotWithSummary:
        reference = await self._reference(server_id)
        paths = await resolve_paths(reference.data_path, selection, include_mcc=True)
        if not paths:
            raise SelectionResolutionError("选择范围没有解析到任何文件路径")
        holder = LockHolder(ServerOperationKind.BACKUP, datetime.now(UTC), user_id, f"世界快照（{_selection_label(selection)}）")
        claims = await self._claims(reference, paths)
        async with self._lock.lease([server_id], holder, claims=claims) as lease:
            assert lease is not None
            await self._revalidate(reference)
            require_same_claims(claims, await self._claims(reference, paths))
            return await self._backups.backup(paths, actor_id=user_id, parent=lease, allow_missing=True)

    async def list_eligible_snapshots(self, server_id: str, selection: RestorationSelection) -> list[ResticSnapshot]:
        paths = await self._resolve_eligibility_paths(server_id, selection)
        return await self._snapshots.find_snapshots_covering(paths) if paths else []

    async def begin_restore(
        self,
        server_id: str,
        source_snapshot_id: str,
        selection: RestorationSelection,
        user_id: int | None,
        is_rollback: bool = False,
        absent_source_dirs: list[str] | None = None,
        reference: ServerRef | None = None,
        world_roots: list[str] | None = None,
    ) -> AsyncGenerator[RestoreEvent]:
        """Acquire RESTORE lock, take a safety snapshot, persist a row, and run the scope flow."""
        reference = reference or await self._reference(server_id)
        paths = await resolve_paths(reference.data_path, selection, include_mcc=True, include_missing=True,
                                    allow_missing_dimension=is_rollback, world_roots=world_roots)
        absent_dirs = await absent_directories(reference.data_path, paths, selection)
        async def restore_file_claims(current_paths: list[Path]) -> list[ResourceClaim]:
            missing = await absent_directories(reference.data_path, current_paths, selection)
            missing_paths = [await confined_history_path(reference.data_path, relative) for relative in missing]
            return await self._claims(reference, [*current_paths, *missing_paths, reference.data_path / ".mcmap" / "tiles"])
        file_claims = await restore_file_claims(paths)
        claims = [*file_claims, ResourceClaim(ResourceKind.MAP_CACHE, server_id)]
        restoration_id = secrets.token_hex(16)
        selection_label = _selection_label(selection)
        holder = LockHolder(
            kind=ServerOperationKind.RESTORE,
            started_at=datetime.now(UTC),
            user_id=user_id,
            description=f"世界恢复（{selection_label}{'，回档' if is_rollback else ''}）",
            restoration_id=restoration_id,
        )

        from ..operations.context import record_phase, retain_recovery_reference
        from ..operations.execution import operation_scope
        from ..operations.journal_types import OperationState

        async with (
            operation_scope("world_restore", [server_id], actor_id=user_id, legacy_id=restoration_id, claims=claims) as operation,
            self._lock.lease([server_id], holder, claims=claims) as lease,
            settle_before_release(),
        ):
            assert lease is not None
            await self._revalidate(reference)
            await self._ensure_server_stopped(server_id)
            current_paths = await resolve_paths(reference.data_path, selection, include_mcc=True, include_missing=True,
                                                allow_missing_dimension=is_rollback, world_roots=world_roots)
            require_same_claims(file_claims, await restore_file_claims(current_paths))
            if await absent_directories(reference.data_path, current_paths, selection) != absent_dirs:
                raise SelectionResolutionError("世界目录状态已变化，请重新选择后恢复")
            if current_paths != paths:
                raise SelectionResolutionError("世界目录范围已变化，请重新选择后恢复")
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
            async with safety_backup_paths(reference.data_path, paths, selection, absent_dirs) as backup_paths:
                safety = await self._backups.backup(backup_paths, actor_id=user_id, parent=lease)
            safety_snapshot_id = safety.id
            await retain_recovery_reference("safety_snapshot", safety_snapshot_id)
            await retain_recovery_reference("restoration", restoration_id)
            touched_items: list[str] = []
            status = RestorationStatus.INTERRUPTED
            error_message: str | None = "恢复连接已中断"
            try:
                await finalize(self._store.insert(
                        restoration_id=restoration_id,
                        reference=reference,
                        selection=selection,
                        source_snapshot_id=source_snapshot_id,
                        safety_snapshot_id=safety_snapshot_id,
                        is_rollback=is_rollback,
                        user_id=user_id,
                        absent_dirs=absent_dirs,
                        world_roots=[path.relative_to(reference.data_path).as_posix() for path in paths] if selection.type is RestorationType.WORLD else None,
                ))

                yield RestoreEvent(
                    event_type="safety_snapshot",
                    restoration_id=restoration_id,
                    safety_snapshot_id=safety_snapshot_id,
                    message=f"安全快照 {safety.short_id}",
                )

                await record_phase("restoring_world", changed=True)
                if selection.type is RestorationType.CHUNKS:
                    flow = self._executor._flow_chunks(
                        data_path=reference.data_path, source_snapshot_id=source_snapshot_id,
                        selection=selection, restoration_id=restoration_id,
                        allow_missing_dimension=is_rollback,
                    )
                else:
                    flow = self._executor._flow_filesystem_restore(
                        source_snapshot_id=source_snapshot_id, paths=paths,
                        restoration_id=restoration_id, touched_items=touched_items,
                    )
                async with aclosing(flow):
                    async for event in flow:
                        yield event
                if absent_source_dirs:
                    await self._executor._restore_absent_sidecars(reference.data_path, source_snapshot_id, selection, absent_source_dirs, paths)
                status = RestorationStatus.SUCCEEDED
                error_message = None
            except Exception as exc:  # noqa: BLE001 - persist safe failure text before closing the stream
                status = RestorationStatus.FAILED
                error_message = public_error_message(exc)
                log_safe_error(exc, f"world restore failed: restoration={restoration_id}")
            finally:
                async def cleanup() -> None:
                    nonlocal status, error_message
                    with CancelScope(shield=True):
                        try:
                            await self._invalidate_map_cache(
                                server_id=server_id, selection=selection, touched_items=touched_items,
                                uncertain=status is not RestorationStatus.SUCCEEDED,
                            )
                        except Exception as exc:  # noqa: BLE001 - cache failure must not skip restoration history
                            from ..operations.context import mark_cache_degraded

                            await mark_cache_degraded(server_id)
                            log_safe_error(exc, f"restore cache invalidation failed: restoration={restoration_id}")
                            if status is RestorationStatus.SUCCEEDED:
                                status = RestorationStatus.FAILED
                                error_message = "世界数据已恢复，但地图缓存更新失败，请检查操作恢复记录"
                        await self._store.finish(restoration_id, status, error_message)
                        if operation is not None and status is not RestorationStatus.SUCCEEDED:
                            operation.outcome = (
                                OperationState.INTERRUPTED if status is RestorationStatus.INTERRUPTED
                                else OperationState.FAILED
                            )

                await finalize(cleanup())

            if status is RestorationStatus.FAILED:
                yield RestoreEvent(event_type="error", restoration_id=restoration_id, message=error_message)
                return
            yield RestoreEvent(event_type="invalidate_cache", restoration_id=restoration_id, message="地图缓存已失效")
            yield RestoreEvent(event_type="complete", restoration_id=restoration_id, message="恢复完成")

    async def rollback(self, restoration_id: str, user_id: int | None) -> AsyncGenerator[RestoreEvent]:
        row = await self._store.get(restoration_id)
        if row is None:
            raise RestoreError(f"恢复记录不存在: {restoration_id}")
        reference = await self._reference(row.server_id)
        require_restoration_owner(row, reference)
        if not row.safety_snapshot_id:
            raise RestoreError("恢复记录没有可用于回档的安全快照")
        selection = RestorationSelection.model_validate_json(row.selection_json)
        recorded = json.loads(row.selection_json)
        roots = recorded.get("world_roots")
        if selection.type is RestorationType.WORLD and roots is None:
            snapshot = await self._snapshots.get_snapshot(row.safety_snapshot_id)
            roots = []
            for value in snapshot.paths:
                path = Path(value)
                if not path.is_relative_to(reference.data_path) or path == reference.data_path:
                    raise SelectionResolutionError("安全快照中的世界范围不明确，请核对后手动恢复")
                relative = path.relative_to(reference.data_path).as_posix()
                await confined_history_path(reference.data_path, relative)
                roots.append(relative)
        if selection.type is RestorationType.WORLD and not roots:
            raise SelectionResolutionError("恢复记录没有可确认的世界范围")
        async with aclosing(self.begin_restore(
            server_id=row.server_id, source_snapshot_id=row.safety_snapshot_id,
            selection=selection, user_id=user_id, is_rollback=True, reference=reference,
            absent_source_dirs=recorded.get("absent_directories", recorded.get("absent_sidecar_dirs", [])),
            world_roots=roots,
        )) as events:
            async for event in events:
                yield event

    async def begin_preview(self, server_id: str, source_snapshot_id: str, selection: RestorationSelection) -> AsyncGenerator[PreviewEvent]:
        reference = await self._reference(server_id)
        async with operation_scope("world_preview", [server_id], claims=[ResourceClaim(ResourceKind.MAP_CACHE, server_id)]):
            await self._revalidate(reference)
            async with aclosing(self._previews.begin_preview(server_id, reference.data_path, source_snapshot_id, selection, reference.generation)) as events:
                async for event in events:
                    yield event

    async def require_preview_owner(self, server_id: str, session_id: str, *, missing_ok: bool = False) -> None:
        from .preview import PreviewSessionNotFoundError

        session = self._preview_manager.get_session(session_id)
        if session is None:
            if missing_ok:
                return
            raise PreviewSessionNotFoundError(session_id)
        reference = await self._reference(server_id)
        if session.server_id != server_id or session.server_generation != reference.generation:
            raise PreviewSessionNotFoundError(session_id)

    async def _resolve_paths_for_selection(self, server_id: str, selection: RestorationSelection) -> list[Path]:
        reference = await self._reference(server_id)
        return await resolve_paths(reference.data_path, selection, include_mcc=True)

    async def _resolve_eligibility_paths(self, server_id: str, selection: RestorationSelection) -> list[Path]:
        reference = await self._reference(server_id)
        return await resolve_paths(reference.data_path, selection, include_mcc=False)

    async def _invalidate_map_cache(self, *, server_id: str, selection: RestorationSelection, touched_items: list[str], uncertain: bool = False) -> int:
        reference = await self._reference(server_id)
        return await invalidate_map_cache(data_path=reference.data_path, selection=selection, touched_items=touched_items, uncertain=uncertain)

    async def request_preview_tile(self, session_id: str, rx: int, rz: int, *, timeout: float | None = None) -> Path:
        return await self._previews.request_preview_tile(session_id, rx, rz, timeout=timeout)

    async def read_preview_tile(self, session_id: str, rx: int, rz: int, *, timeout: float | None = None) -> bytes:
        return await self._previews.read_preview_tile(session_id, rx, rz, timeout=timeout)

    async def end_preview(self, session_id: str) -> None:
        await self._preview_manager.end(session_id)

    def heartbeat_preview(self, session_id: str) -> None:
        self._preview_manager.heartbeat(session_id)

    async def get_preview_tile(
        self, session_id: str, rx: int, rz: int
    ) -> Path | None:
        return await self._preview_manager.get_tile_path(session_id, rx, rz)

    def get_preview_session_dir(self, session_id: str) -> Path | None:
        return self._preview_manager.get_session_dir(session_id)

    def start_janitor(self) -> asyncio.Task:
        return self._preview_manager.start_janitor()

    async def stop_janitor(self) -> None:
        await self._preview_manager.stop_janitor()

    async def close(self, *, preserve_artifacts: bool = False) -> None:
        await self._preview_manager.close(preserve_artifacts=preserve_artifacts)

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
