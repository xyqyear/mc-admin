import errno
import json
import secrets
from collections.abc import AsyncGenerator, Sequence
from contextlib import ExitStack, aclosing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import aiofiles.os as aioos
from fastapi import HTTPException

from ..background_tasks import TaskProgress, TaskType
from ..background_tasks.manager import BackgroundTaskManager
from ..files.resources import path_claims
from ..minecraft import DockerMCManager
from ..operation_admission import get_server_write_admission
from ..operations.context import (
    record_phase,
    retain_recovery_reference,
    revalidate_targets,
)
from ..operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from ..operations.execution import settle_before_release
from ..operations.finalization import finalize
from ..operations.journal_types import OperationState, RecoveryReference
from ..runtime_resources import current_runtime
from ..utils import async_fs
from ..world.artifacts import restore_stage
from ..world.locks import LockHolder, ServerOperationKind, ServerOperationLock
from .coverage import covers
from .file_restore import FileRestoreAdapter
from .protection import SnapshotProtection
from .restoration_models import RestorationStatus
from .restoration_store import RestorationStore, SessionFactory, restoration_status
from .scopes import (
    GlobalScope,
    ResolvedScope,
    ServerScope,
    SnapshotScope,
    WorldScope,
    resolve_scope,
    scope_adapter,
)
from .service import SnapshotService


@dataclass(frozen=True)
class PreparedSnapshot:
    resolved: ResolvedScope
    protection: SnapshotProtection
    maintenance: tuple[str, ...]
    claims: tuple[ResourceClaim, ...]
    missing_parents: tuple[Path, ...]


class SnapshotCommands:
    def __init__(
        self,
        snapshots: SnapshotService,
        manager: DockerMCManager,
        lock: ServerOperationLock,
        tasks: BackgroundTaskManager,
        sessions: SessionFactory,
        root: Path,
    ) -> None:
        self.snapshots = snapshots
        self._manager = manager
        self._lock = lock
        self._tasks = tasks
        self._sessions = sessions
        self._root = root
        self.store = RestorationStore(sessions)
        self._files = FileRestoreAdapter(manager, lock)
        self._active: dict[str, ResolvedScope] = {}

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

    async def prepare(
        self,
        scope: SnapshotScope,
        *,
        restoring: bool = False,
        retained: Sequence[Path] = (),
    ) -> PreparedSnapshot:
        resolved = await resolve_scope(scope, root=self._root, sessions=self._sessions)
        protection = await self.snapshots.protection(
            retained=retained,
            data_paths=[ref.data_path for ref in resolved.servers],
        )
        protection.require_targets(resolved.paths)
        maintenance = (
            tuple(ref.server_id for ref in resolved.servers)
            if not restoring or isinstance(scope, (GlobalScope, ServerScope))
            else tuple(await self._files.maintenance_servers(resolved.paths))
        )
        claims = set(resolved.claims)
        missing_parents: set[Path] = set()
        for path in resolved.paths:
            for parent in path.parents:
                if not parent.is_relative_to(self._root) or await async_fs.lexists(
                    parent
                ):
                    break
                missing_parents.add(parent)
        for ref in resolved.servers:
            parents = [
                path
                for path in missing_parents
                if path.is_relative_to(ref.project_path)
            ]
            claims.update(
                await path_claims(ref.project_path, parents, server_id=ref.server_id)
            )
            if restoring and ref.server_id in maintenance:
                claims.add(ResourceClaim(ResourceKind.MAP_CACHE, ref.server_id))
                claims.update(
                    await path_claims(
                        ref.project_path,
                        [ref.data_path / ".mcmap" / "tiles"],
                        server_id=ref.server_id,
                    )
                )
        claims.update(
            ResourceClaim(ResourceKind.MAINTENANCE, name) for name in maintenance
        )
        return PreparedSnapshot(
            resolved,
            protection,
            maintenance,
            tuple(sorted(claims)),
            tuple(sorted(missing_parents)),
        )

    async def _revalidate(self, prepared: PreparedSnapshot) -> None:
        await revalidate_targets()
        current = await resolve_scope(
            prepared.resolved.scope, root=self._root, sessions=self._sessions
        )
        if current != prepared.resolved:
            raise HTTPException(
                status_code=409, detail="目标路径或服务器实例已变化，请重新确认操作"
            )
        await self.snapshots.revalidate_protection(prepared.protection)

    def _retain(self, stack: ExitStack, task_id: str, resolved: ResolvedScope) -> None:
        admission = get_server_write_admission()
        stack.enter_context(
            admission.write_global()
            if isinstance(resolved.scope, GlobalScope)
            else admission.write([ref.server_id for ref in resolved.servers])
        )
        self._active[task_id] = resolved
        stack.callback(self._active.pop, task_id, None)

    async def create(self, scope: SnapshotScope, actor_id: int) -> dict:
        task_id = secrets.token_hex(16)
        with ExitStack() as stack:
            stack.enter_context(self.snapshots.repository_use.retain())
            prepared = await self.prepare(scope)
            await get_operation_coordinator().check_available(prepared.claims)
            if isinstance(scope, WorldScope) and scope.selection.type.value not in {
                "world",
                "dimension",
            }:
                raise HTTPException(
                    status_code=400, detail="手动快照请选择整个世界或维度"
                )
            for path in prepared.resolved.paths:
                if not await async_fs.lexists(path):
                    raise HTTPException(status_code=404, detail="快照目标不存在")
            self._retain(stack, task_id, prepared.resolved)
            submitted = await self._tasks.submit_durable(
                TaskType.SNAPSHOT_CREATE,
                "创建快照",
                self._create(prepared, actor_id),
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

    async def _create(
        self, prepared: PreparedSnapshot, actor_id: int
    ) -> AsyncGenerator[TaskProgress]:
        yield TaskProgress(message="正在等待快照目标可用")
        holder = LockHolder(
            ServerOperationKind.BACKUP, datetime.now(UTC), actor_id, "创建快照"
        )
        async with (
            self._lock.lease(
                list(prepared.maintenance), holder, claims=prepared.claims
            ),
            settle_before_release(),
        ):
            await self._revalidate(prepared)
            await record_phase("creating_snapshot")
            yield TaskProgress(message="正在读取文件并创建快照")
            snapshot = await self.snapshots.create_snapshot(
                prepared.resolved.paths, protection=prepared.protection
            )
            yield TaskProgress(
                progress=100,
                message="快照创建完成",
                result={
                    "snapshot": snapshot.model_dump(mode="json"),
                    "skipped_paths": self._skipped(prepared),
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
    ) -> dict:
        task_id, restoration_id = secrets.token_hex(16), secrets.token_hex(16)
        with ExitStack() as stack:
            stack.enter_context(self.snapshots.repository_use.retain([source_id]))
            retained: list[Path] = []
            absent: tuple[Path, ...] = ()
            absent_parents: tuple[Path, ...] = ()
            original = None
            if rollback_of_id is not None:
                original = await self.store.get(rollback_of_id)
                if original is None or original.safety_snapshot_id != source_id:
                    raise HTTPException(
                        status_code=409, detail="恢复记录或安全快照已变化"
                    )
                retained = [
                    Path(value)
                    for value in json.loads(original.protection_json or "{}").get(
                        "excluded", []
                    )
                ]
                evidence = json.loads(original.selection_json)
                absent = tuple(Path(path) for path in evidence.get("absent_paths", []))
                absent_parents = tuple(
                    Path(path) for path in evidence.get("absent_parents", [])
                )
            prepared = await self.prepare(scope, restoring=True, retained=retained)
            if isinstance(scope, WorldScope):
                raise HTTPException(status_code=400, detail="请使用地图恢复入口")
            if original is not None:
                saved = json.loads(original.scope_json or "{}")
                targets = json.loads(original.targets_json or "[]")
                current = [
                    {"server_id": ref.server_id, "generation": ref.generation}
                    for ref in prepared.resolved.servers
                ]
                if (
                    original.binding_issue
                    or targets != current
                    or saved.get("paths")
                    != [str(path) for path in prepared.resolved.paths]
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="恢复记录不属于当前路径或服务器实例，无法回滚",
                    )
                for path in (*absent, *absent_parents):
                    if not any(
                        path.is_relative_to(target) or target.is_relative_to(path)
                        for target in prepared.resolved.paths
                    ) or not path.is_relative_to(self._root):
                        raise HTTPException(
                            status_code=409, detail="恢复记录的缺失范围无效"
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
                self._restore(
                    prepared,
                    source_id,
                    restoration_id,
                    actor_id,
                    absent,
                    absent_parents,
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

    async def _restore(
        self,
        prepared: PreparedSnapshot,
        source_id: str,
        restoration_id: str,
        actor_id: int,
        absent: tuple[Path, ...],
        absent_parents: tuple[Path, ...],
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
            await self._revalidate(prepared)
            await self._files.check_stopped(list(prepared.maintenance))
            yield TaskProgress(message="正在检查源快照和保护范围")
            source = await self.snapshots.get_snapshot(source_id)
            protection = await self.snapshots.with_source_protection(
                prepared.protection, source
            )
            protection.require_targets(prepared.resolved.paths)
            prepared = replace(prepared, protection=protection)
            for path in prepared.resolved.paths:
                if path not in absent and not covers(
                    path, [Path(value) for value in source.paths], protection.excluded
                ):
                    raise HTTPException(status_code=400, detail="源快照未覆盖所选范围")
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
            for path in prepared.resolved.paths:
                (present if await async_fs.lexists(path) else missing).append(path)
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
                )
                await self._revalidate(prepared)
                absent = tuple(
                    set(absent)
                    | set(
                        await self.snapshots.absent_targets(
                            source_id, prepared.resolved.paths
                        )
                    )
                )
                touched: list[str] = []
                restored = False
                try:
                    await record_phase("restoring_files", changed=True)
                    yield TaskProgress(
                        progress=0,
                        message="正在恢复所选文件",
                        result={
                            "restoration_id": restoration_id,
                            "safety_snapshot_id": safety.id,
                        },
                    )
                    targets = [
                        path for path in prepared.resolved.paths if path not in absent
                    ]
                    async with aclosing(
                        self.snapshots.restore(
                            source_id, targets, protection=prepared.protection
                        )
                    ) as events:
                        async for event in events:
                            if (
                                event.kind == "file"
                                and event.action in {"updated", "restored", "deleted"}
                                and event.item
                            ):
                                touched.append(event.item)
                            elif event.kind == "status":
                                yield TaskProgress(
                                    progress=(event.percent_done or 0) * 100,
                                    message="正在恢复所选文件",
                                )
                    removed = await self.snapshots.remove_absent_paths(
                        source_id, absent, protection=prepared.protection
                    )
                    touched.extend(str(path) for path in removed)
                    for parent in sorted(
                        absent_parents, key=lambda path: len(path.parts), reverse=True
                    ):
                        if prepared.protection.permits(parent):
                            try:
                                await finalize(aioos.rmdir(parent))
                            except OSError as error:
                                if error.errno not in {errno.ENOTEMPTY, errno.ENOENT}:
                                    raise
                    restored = True
                finally:
                    await finalize(
                        self._files.invalidate(
                            touched,
                            prepared.resolved.servers,
                            [] if restored else prepared.maintenance,
                        )
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
    return current_runtime().resource("snapshot_commands")


def require_snapshot_tasks_finished(server_id: str) -> None:
    commands = get_snapshot_commands()
    if commands is not None:
        commands.require_deletable(server_id)
