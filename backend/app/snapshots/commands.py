import errno
import json
import re
import secrets
from collections.abc import AsyncGenerator
from contextlib import ExitStack, aclosing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import aiofiles.os as aioos
from fastapi import HTTPException

from ..background_tasks import TaskProgress, TaskType
from ..background_tasks.manager import BackgroundTaskManager
from ..errors import PublicOperationError, log_safe_error, public_error_message
from ..files.resources import path_claims
from ..minecraft import DockerMCManager
from ..operation_admission import get_server_write_admission
from ..operations.context import (
    record_phase,
    retain_recovery_reference,
)
from ..operations.coordinator import (
    ConflictPolicy,
    get_operation_coordinator,
)
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from ..operations.journal_types import OperationState, RecoveryReference
from ..runtime_resources import current_runtime
from ..servers.references import resolve_server_ref
from ..utils import async_fs
from ..world.artifacts import restore_stage
from ..world.locks import LockHolder, ServerOperationKind, ServerOperationLock
from ..world.scope_execution import RestoreScopeExecutor
from ..world.selection import confined_history_path, resolve_paths
from .api_models import SnapshotRestoreSource, SnapshotTargetCheck
from .application import SnapshotMaintenanceConflict
from .evidence import absence_tags, snapshot_absence
from .file_restore import FileRestoreAdapter
from .models import ResticSnapshotWithSummary
from .path_mapping import execution_parent_mappings, mapping_json
from .planner import TargetIgnoredError
from .preparation import PreparedSnapshot, SnapshotPlanner
from .preview_models import PreviewBinding
from .previews import SnapshotPreviews, get_snapshot_previews
from .restoration_models import RestorationStatus, RestorationType
from .restoration_store import (
    RestorationStore,
    SessionFactory,
    require_restoration_owner,
    restoration_status,
)
from .scopes import (
    GlobalScope,
    ResolvedScope,
    SnapshotScope,
    WorldScope,
    resolve_scope,
    scope_adapter,
)
from .service import SnapshotService


class SnapshotCommands:
    def __init__(
        self,
        snapshots: SnapshotService,
        manager: DockerMCManager,
        lock: ServerOperationLock,
        tasks: BackgroundTaskManager,
        sessions: SessionFactory,
        root: Path,
        previews: SnapshotPreviews | None = None,
    ) -> None:
        self.snapshots = snapshots
        self._previews = previews
        self._manager = manager
        self._lock = lock
        self._tasks = tasks
        self._sessions = sessions
        self._root = root
        self.store = RestorationStore(sessions)
        self._files = FileRestoreAdapter(manager, lock)
        self._world = RestoreScopeExecutor(snapshots)
        self._planner = SnapshotPlanner(snapshots, self._files, sessions, root)
        self._active: dict[str, ResolvedScope] = {}

    async def check_world_target(self, scope: WorldScope) -> SnapshotTargetCheck:
        resolved = await resolve_scope(
            scope, root=self._root, sessions=self._sessions, include_mcc=False
        )
        protection = await self.snapshots.protection(
            data_paths=[ref.data_path for ref in resolved.servers]
        )
        try:
            protection.select_targets(resolved.paths)
            await self._planner.require_permitted_chunks(resolved, protection)
        except TargetIgnoredError:
            return SnapshotTargetCheck(
                allowed=False, reason="此范围已被快照规则忽略，不能创建快照或恢复"
            )
        skipped = set(protection.skipped_under(resolved.paths))
        selected_chunks = set(scope.selection.chunks)
        selected_paths = set(resolved.paths)
        for path in protection.excluded:
            match = re.fullmatch(r"c\.(-?\d+)\.(-?\d+)\.mcc", path.name)
            if match is None:
                continue
            x, z = map(int, match.groups())
            if selected_chunks and (x, z) not in selected_chunks:
                continue
            if path.with_name(f"r.{x // 32}.{z // 32}.mca") in selected_paths:
                skipped.add(path)
        return SnapshotTargetCheck(
            allowed=True,
            skipped_paths=[str(path) for path in sorted(skipped)[:100]],
            skipped_count=len(skipped),
        )

    def require_deletable(self, server_id: str) -> None:
        for task_id, resolved in self._active.items():
            if isinstance(resolved.scope, GlobalScope) or any(
                ref.server_id == server_id for ref in resolved.servers
            ):
                raise HTTPException(
                    status_code=423,
                    detail={
                        "code": "snapshot_task_active",
                        "task_id": task_id,
                        "message": "快照或恢复任务尚未结束，请等待完成后再删除服务器",
                    },
                )

    def _retain(self, stack: ExitStack, task_id: str, resolved: ResolvedScope) -> None:
        admission = get_server_write_admission()
        stack.enter_context(
            admission.write_global()
            if isinstance(resolved.scope, GlobalScope)
            else admission.write([ref.server_id for ref in resolved.servers])
        )
        self._active[task_id] = resolved
        stack.callback(self._active.pop, task_id, None)

    async def create(self, scope: SnapshotScope, actor_id: int, note: str = "") -> dict:
        task_id = secrets.token_hex(16)
        with ExitStack() as stack:
            stack.enter_context(self.snapshots.repository_use.retain())
            prepared = await self._planner.prepare(scope)
            await get_operation_coordinator().check_available(prepared.claims)
            if isinstance(scope, WorldScope) and scope.selection.type.value not in {
                "world",
                "dimension",
            }:
                raise HTTPException(
                    status_code=400, detail="手动快照请选择整个世界或维度"
                )
            for path in prepared.paths:
                if not isinstance(scope, WorldScope) and not await async_fs.lexists(
                    path
                ):
                    raise HTTPException(status_code=404, detail="快照目标不存在")
            self._retain(stack, task_id, prepared.resolved)
            submitted = await self._tasks.submit_durable(
                TaskType.SNAPSHOT_CREATE,
                "创建快照",
                self._create(prepared, actor_id, note=note),
                server_id=None if isinstance(scope, GlobalScope) else scope.server_id,
                server_refs=prepared.resolved.servers,
                claims=prepared.claims,
                require_existing_targets=not isinstance(scope, GlobalScope),
                actor_id=actor_id,
                task_id=task_id,
                exclusive_key=f"snapshot-create:{scope.model_dump_json()}",
            )
            retained = stack.pop_all()
            submitted.awaitable.add_done_callback(lambda _: retained.close())
        return {"task_id": task_id, "skipped_paths": self._skipped(prepared)}

    async def backup(
        self, scope: SnapshotScope, actor_id: int | None = None
    ) -> ResticSnapshotWithSummary:
        with self.snapshots.repository_use.retain():
            prepared = await self._planner.prepare(scope)
            for path in prepared.paths:
                if not await async_fs.lexists(prepared.protection.execution_path(path)):
                    raise HTTPException(status_code=404, detail="快照目标不存在")
            snapshot = None
            async with (
                operation_scope(
                    "snapshot_backup",
                    [ref.server_id for ref in prepared.resolved.servers],
                    actor_id=actor_id,
                    claims=prepared.claims,
                ),
                aclosing(
                    self._create(prepared, actor_id, ConflictPolicy.SKIP)
                ) as progress,
            ):
                async for event in progress:
                    if event.result is not None and "snapshot" in event.result:
                        snapshot = ResticSnapshotWithSummary.model_validate(
                            event.result["snapshot"]
                        )
            if snapshot is not None:
                return snapshot
        raise RuntimeError("快照执行结束但没有返回结果")

    async def eligible(self, scope: SnapshotScope) -> list[SnapshotRestoreSource]:
        prepared = await self._planner.prepare(scope)
        paths = prepared.paths
        if isinstance(scope, WorldScope):
            paths = tuple(
                path
                for path in await resolve_paths(
                    prepared.resolved.servers[0].data_path,
                    scope.selection,
                    include_mcc=False,
                )
                if prepared.protection.permits(path)
            )
        prepared.protection.select_targets(paths)
        eligible = []
        for source in await self.snapshots.list_snapshots():
            try:
                protection = await self.snapshots.with_source_protection(
                    prepared.protection, source
                )
            except HTTPException as error:
                if error.status_code == 409:
                    continue
                raise
            try:
                allowed = protection.select_targets(paths)
            except TargetIgnoredError:
                continue
            absent = snapshot_absence(source)
            if allowed and all(
                any(path.is_relative_to(parent) for parent in absent)
                or self.snapshots.source_covers(source, path, protection)
                for path in allowed
            ):
                skipped = protection.skipped_under(prepared.resolved.paths)
                eligible.append(SnapshotRestoreSource(
                    **source.model_dump(),
                    skipped_paths=[str(path) for path in skipped[:100]],
                    skipped_count=len(skipped),
                ))
        return eligible

    async def _create(
        self,
        prepared: PreparedSnapshot,
        actor_id: int | None,
        policy: ConflictPolicy = ConflictPolicy.WAIT,
        *,
        note: str = "",
    ) -> AsyncGenerator[TaskProgress]:
        yield TaskProgress(message="正在等待快照目标可用")
        holder = LockHolder(
            ServerOperationKind.BACKUP, datetime.now(UTC), actor_id, "创建快照"
        )
        async with self._lock.lease(
            list(prepared.maintenance),
            holder,
            claims=prepared.claims,
            policy=policy,
        ) as lease:
            if lease is None:
                raise SnapshotMaintenanceConflict("服务器正在维护")
            async with settle_before_release():
                await self._planner.revalidate(prepared)
                await record_phase("creating_snapshot")
                yield TaskProgress(message="正在读取文件并创建快照")
                paths = [
                    path
                    for path in prepared.paths
                    if await async_fs.lexists(prepared.protection.execution_path(path))
                ]
                prepared.protection.select_targets(paths)
                missing = [path for path in prepared.paths if path not in paths]
                snapshot = await self.snapshots.create_snapshot(
                    paths, protection=prepared.protection, tags=absence_tags(missing)
                )
                note_warning = None
                if note:
                    try:
                        await finalize(self.snapshots.save_note(snapshot.id, note))
                        snapshot.note = note
                    except Exception as error:  # noqa: BLE001 - Committed snapshots survive metadata failures.
                        log_safe_error(error, "Snapshot note persistence failed")
                        note_warning = "快照已创建，但备注保存失败；请仅重试保存备注"
                yield TaskProgress(
                    progress=100,
                    message=note_warning or "快照创建完成",
                    result={
                        "snapshot": snapshot.model_dump(mode="json"),
                        "skipped_paths": self._skipped(prepared),
                        "note_warning": note_warning,
                    },
                )

    @staticmethod
    def _skipped(prepared: PreparedSnapshot) -> list[str]:
        return [
            str(path)
            for path in prepared.protection.skipped_under(prepared.resolved.paths)
        ]

    async def restore(
        self,
        scope: SnapshotScope,
        source_id: str,
        actor_id: int,
        *,
        entry_point: str = "files",
        rollback_of_id: str | None = None,
        preview_id: str | None = None,
    ) -> dict:
        task_id, restoration_id = secrets.token_hex(16), secrets.token_hex(16)
        with ExitStack() as stack:
            stack.enter_context(self.snapshots.repository_use.retain([source_id]))
            retained: list[Path] = []
            absent: tuple[Path, ...] = ()
            absent_parents: tuple[Path, ...] = ()
            history_paths = None
            legacy_world = False
            original = None
            evidence: dict = {}
            if rollback_of_id is not None:
                original = await self.store.get(rollback_of_id)
                if original is None or original.safety_snapshot_id != source_id:
                    raise HTTPException(
                        status_code=409, detail="恢复记录或安全快照已变化"
                    )
                recorded_protection = json.loads(original.protection_json or "{}")
                retained = [
                    Path(value) for value in recorded_protection.get("excluded", [])
                ]
                evidence = json.loads(original.selection_json)
                absent = tuple(Path(path) for path in evidence.get("absent_paths", []))
                absent_parents = tuple(
                    Path(path) for path in evidence.get("absent_parents", [])
                )
                if isinstance(scope, WorldScope):
                    async with self._sessions() as session:
                        ref = await resolve_server_ref(
                            session, scope.server_id, servers_root=self._root
                        )
                    require_restoration_owner(original, ref)
                    saved_paths = json.loads(original.scope_json or "{}").get("paths")
                    if saved_paths is not None:
                        history_paths = tuple(Path(path) for path in saved_paths)
                    elif scope.selection.type is RestorationType.WORLD:
                        roots = evidence.get("world_roots")
                        legacy_world = roots is None
                        history_paths = (
                            (ref.data_path,)
                            if roots is None
                            else tuple(
                                [
                                    await confined_history_path(ref.data_path, value)
                                    for value in roots
                                ]
                            )
                        )
                    old_absent = evidence.get(
                        "absent_directories", evidence.get("absent_sidecar_dirs", [])
                    )
                    absent_parents = tuple(
                        set(absent_parents)
                        | {
                            await confined_history_path(ref.data_path, value)
                            for value in old_absent
                        }
                    )
            prepared = await self._planner.prepare(
                scope,
                restoring=True,
                retained=retained,
                history_paths=history_paths,
                from_history=original is not None,
                legacy_world=legacy_world,
                source=await self.snapshots.get_snapshot(source_id),
            )
            if original is not None:
                saved = json.loads(original.scope_json or "{}")
                targets = json.loads(original.targets_json or "[]")
                current = [
                    {"server_id": ref.server_id, "generation": ref.generation}
                    for ref in prepared.resolved.servers
                ]
                expected_paths = [str(path) for path in prepared.resolved.paths]
                if (
                    original.binding_issue
                    or targets != current
                    or (
                        saved.get("paths") is not None
                        and saved["paths"] != expected_paths
                    )
                    or (
                        saved.get("mappings") is not None
                        and saved["mappings"]
                        != mapping_json(prepared.resolved.mappings)
                    )
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="恢复记录不属于当前路径或服务器实例，无法回滚",
                    )
                targets = set(prepared.resolved.paths)
                for path in absent:
                    if not any(
                        parent in targets for parent in (path, *path.parents)
                    ) or not path.is_relative_to(self._root):
                        raise HTTPException(
                            status_code=409, detail="恢复记录的缺失范围无效"
                        )
                for path in absent_parents:
                    if not any(
                        target.is_relative_to(path)
                        for target in prepared.resolved.execution_paths
                    ) or not path.is_relative_to(self._root):
                        raise HTTPException(
                            status_code=409, detail="恢复记录的缺失范围无效"
                        )
                parent_mappings = execution_parent_mappings(
                    absent_parents, prepared.resolved.mappings
                )
                if evidence.get("absent_parent_mappings") is not None and evidence[
                    "absent_parent_mappings"
                ] != mapping_json(parent_mappings):
                    raise HTTPException(
                        status_code=409, detail="恢复记录的缺失父目录映射已变化"
                    )
                claims = set(prepared.claims)
                for ref in prepared.resolved.servers:
                    claims.update(
                        await path_claims(
                            ref.project_path,
                            [
                                p
                                for p in absent_parents
                                if p.is_relative_to(ref.project_path)
                            ],
                            server_id=ref.server_id,
                        )
                    )
                prepared = replace(prepared, claims=tuple(sorted(claims)))
            preview_binding = None
            if preview_id is not None:
                if self._previews is None:
                    raise HTTPException(status_code=503, detail="预览服务不可用")
                preview_binding = await self._previews.validate(
                    preview_id, prepared, source_id
                )
            for reference in prepared.resolved.servers:
                get_server_write_admission().check(reference.server_id)
            await self._files.check_available(list(prepared.maintenance))
            await get_operation_coordinator().check_available(prepared.claims)
            self._retain(stack, task_id, prepared.resolved)

            async def accepted(operation_id: str) -> None:
                await self.store.accept(
                    restoration_id=restoration_id,
                    operation_id=operation_id,
                    resolved=prepared.resolved,
                    source_snapshot_id=source_id,
                    protection_json=prepared.protection.to_json(),
                    entry_point=entry_point,
                    user_id=actor_id,
                    rollback_of_id=rollback_of_id,
                )
                if self._tasks.journal is not None:
                    await self._tasks.journal.phase(
                        operation_id,
                        "accepted",
                        recovery_refs=(
                            RecoveryReference("source_snapshot", source_id),
                            RecoveryReference("restoration", restoration_id),
                        ),
                    )

            submitted = await self._tasks.submit_durable(
                TaskType.SNAPSHOT_RESTORE,
                "回滚恢复" if rollback_of_id else "恢复快照",
                self._record_errors(
                    restoration_id,
                    self._restore(
                        prepared,
                        source_id,
                        restoration_id,
                        actor_id,
                        absent,
                        absent_parents,
                        preview_binding,
                    ),
                ),
                server_id=None if isinstance(scope, GlobalScope) else scope.server_id,
                server_refs=prepared.resolved.servers,
                claims=prepared.claims,
                require_existing_targets=not isinstance(scope, GlobalScope),
                actor_id=actor_id,
                task_id=task_id,
                exclusive_key=f"snapshot-restore:{scope.model_dump_json()}",
                on_accepted=accepted,
                on_finished=lambda state: self.store.finish_operation(
                    restoration_id, state
                ),
            )
            references = stack.pop_all()
            submitted.awaitable.add_done_callback(lambda _: references.close())
        return {
            "task_id": task_id,
            "restoration_id": restoration_id,
            "skipped_paths": self._skipped(prepared),
        }

    async def rollback(self, restoration_id: str, actor_id: int) -> dict:
        row = await self.store.get(restoration_id)
        if row is None:
            raise HTTPException(status_code=404, detail="恢复记录不存在")
        status = row.status
        if row.operation_id and self._tasks.journal is not None:
            operation = await self._tasks.journal.get(row.operation_id)
            if operation is not None:
                status = restoration_status(OperationState(operation.state))
                if operation.blocked_reason or (
                    status not in {RestorationStatus.PENDING, RestorationStatus.RUNNING}
                    and not operation.writers_stopped
                ):
                    raise HTTPException(
                        status_code=423, detail="请先在操作历史中完成写入状态核对"
                    )
        if status in {RestorationStatus.PENDING, RestorationStatus.RUNNING}:
            raise HTTPException(status_code=409, detail="请等待恢复任务结束后再回滚")
        if not row.safety_snapshot_id or not row.scope_json:
            raise HTTPException(
                status_code=409, detail="此恢复记录没有可用的安全快照或范围信息"
            )
        scope = scope_adapter.validate_python(json.loads(row.scope_json)["scope"])
        return await self.restore(
            scope,
            row.safety_snapshot_id,
            actor_id,
            entry_point="history",
            rollback_of_id=row.id,
        )

    async def _record_errors(
        self,
        restoration_id: str,
        worker: AsyncGenerator[TaskProgress],
    ) -> AsyncGenerator[TaskProgress]:
        try:
            async with aclosing(worker):
                async for progress in worker:
                    yield progress
        except Exception as error:
            await self.store.save_error(restoration_id, public_error_message(error))
            raise

    async def _restore(
        self,
        prepared: PreparedSnapshot,
        source_id: str,
        restoration_id: str,
        actor_id: int,
        absent: tuple[Path, ...],
        absent_parents: tuple[Path, ...],
        preview_binding: PreviewBinding | None = None,
    ) -> AsyncGenerator[TaskProgress]:
        yield TaskProgress(
            message="正在等待恢复目标可用", result={"restoration_id": restoration_id}
        )
        holder = LockHolder(
            ServerOperationKind.RESTORE,
            datetime.now(UTC),
            actor_id,
            "恢复快照",
            restoration_id,
        )
        async with (
            self._lock.lease(
                list(prepared.maintenance), holder, claims=prepared.claims
            ),
            settle_before_release(),
        ):
            await self._planner.revalidate(prepared)
            if preview_binding is not None and self._previews is not None:
                await self._previews.validate_binding(
                    preview_binding, prepared, source_id
                )
            await self._files.check_stopped(list(prepared.maintenance))
            yield TaskProgress(message="正在检查源快照和保护范围")
            source = await self.snapshots.get_snapshot(source_id)
            scope = prepared.resolved.scope
            selection = scope.selection if isinstance(scope, WorldScope) else None
            if prepared.legacy_world:
                ref = prepared.resolved.servers[0]
                roots = tuple(Path(path) for path in source.paths)
                if not roots or any(
                    path == ref.data_path or not path.is_relative_to(ref.data_path)
                    for path in roots
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="安全快照中的世界范围不明确，请核对后手动恢复",
                    )
                narrowed = await self._planner.prepare(
                    scope,
                    restoring=True,
                    retained=prepared.protection.excluded,
                    history_paths=roots,
                    from_history=True,
                )
                prepared = replace(narrowed, claims=prepared.claims)
                await self.store.save_scope(restoration_id, prepared.resolved)
            prepared, absent = await self._planner.with_source(
                prepared, source, absent, absent_parents
            )
            protection = prepared.protection
            await self.store.save_protection(restoration_id, protection.to_json())
            yield TaskProgress(
                message="正在创建恢复前的安全快照",
                result={
                    "restoration_id": restoration_id,
                    "skipped_paths": self._skipped(prepared),
                },
            )
            await record_phase("safety_snapshot")
            present, missing = [], []
            paths = prepared.paths
            existing = await async_fs.lexists_many(
                [prepared.protection.execution_path(path) for path in paths]
            )
            for path, exists in zip(paths, existing, strict=True):
                (present if exists else missing).append(path)
            if present:
                safety = await self.snapshots.create_snapshot(
                    present, protection=prepared.protection
                )
            else:
                async with restore_stage() as stage:
                    marker = stage / "absence.json"
                    async with aiofiles.open(marker, "w") as stream:
                        await stream.write(json.dumps([str(path) for path in missing]))
                    safety = await self.snapshots.create_snapshot(
                        [marker], protection=prepared.protection
                    )
            with self.snapshots.repository_use.retain([safety.id]):
                await retain_recovery_reference("safety_snapshot", safety.id)
                missing_parents = [
                    str(path)
                    for path in prepared.missing_parents
                    if not await async_fs.lexists(path)
                ]
                await self.store.save_safety(
                    restoration_id,
                    safety.id,
                    [str(p) for p in missing],
                    missing_parents,
                    mapping_json(
                        execution_parent_mappings(
                            [Path(path) for path in missing_parents],
                            prepared.resolved.mappings,
                        )
                    ),
                )
                await self._planner.revalidate(prepared)
                if preview_binding is not None and self._previews is not None:
                    await self._previews.validate_binding(
                        preview_binding, prepared, source_id
                    )
                absent = tuple(
                    set(absent)
                    | set(
                        await self.snapshots.absent_targets(
                            source_id, prepared.paths, protection=prepared.protection
                        )
                    )
                )
                touched: list[str] = []
                restored = False
                try:
                    await record_phase(
                        "restoring_world" if selection else "restoring_files",
                        changed=True,
                    )
                    yield TaskProgress(
                        progress=0,
                        message="正在恢复所选文件",
                        result={
                            "restoration_id": restoration_id,
                            "safety_snapshot_id": safety.id,
                        },
                    )
                    if selection and selection.type is RestorationType.CHUNKS:
                        async with aclosing(
                            self._world.restore_chunks(
                                data_path=prepared.resolved.servers[0].data_path,
                                source_snapshot_id=source_id,
                                selection=selection,
                                allow_missing_dimension=prepared.from_history,
                                protection=protection,
                            )
                        ) as events:
                            async for event in events:
                                yield event
                        for path in absent:
                            execution_path = protection.execution_path(path)
                            if (
                                path.suffix == ".mca"
                                and protection.permits(path)
                                and await aioos.path.isfile(execution_path)
                            ):
                                async with aiofiles.open(
                                    execution_path, "rb"
                                ) as stream:
                                    empty = await stream.read(4096) == bytes(4096)
                                if empty:
                                    await finalize(aioos.remove(execution_path))
                    else:
                        async with aclosing(
                            self._files.apply(
                                self.snapshots,
                                source_id,
                                prepared.paths,
                                absent,
                                protection,
                                touched,
                            )
                        ) as progress:
                            async for event in progress:
                                yield event
                    for parent in sorted(
                        absent_parents, key=lambda path: len(path.parts), reverse=True
                    ):
                        parent_mappings = execution_parent_mappings(
                            [parent], prepared.resolved.mappings
                        )
                        if any(
                            protection.permits(item.logical) for item in parent_mappings
                        ):
                            try:
                                await finalize(aioos.rmdir(parent))
                            except OSError as error:
                                if error.errno not in {errno.ENOTEMPTY, errno.ENOENT}:
                                    raise
                    restored = True
                finally:
                    try:
                        await finalize(
                            self._files.invalidate(
                                touched,
                                prepared.resolved.servers,
                                [] if restored else prepared.maintenance,
                                selection=selection,
                            )
                        )
                    except Exception as error:
                        if restored:
                            raise PublicOperationError(
                                "数据已恢复，但地图缓存更新失败；请重新初始化地图"
                            ) from error
                        raise
                if selection:
                    from ..self_check.constants import (
                        WORLD_RESTORED_TRIGGER,
                        WORLD_ROLLED_BACK_TRIGGER,
                    )
                    from ..self_check.events import schedule_self_check_event

                    schedule_self_check_event(
                        WORLD_ROLLED_BACK_TRIGGER
                        if prepared.from_history
                        else WORLD_RESTORED_TRIGGER,
                        actor_id,
                    )
                yield TaskProgress(
                    progress=100,
                    message="恢复完成",
                    result={
                        "restoration_id": restoration_id,
                        "safety_snapshot_id": safety.id,
                        "skipped_paths": self._skipped(prepared),
                    },
                )


def get_snapshot_commands() -> SnapshotCommands | None:
    return current_runtime().snapshot_commands


def require_snapshot_tasks_finished(server_id: str) -> None:
    commands = get_snapshot_commands()
    if commands is not None:
        commands.require_deletable(server_id)
    previews = get_snapshot_previews()
    if previews is not None:
        previews.require_deletable(server_id)
