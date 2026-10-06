"""Task-owned preparation and bounded observation of snapshot previews."""

import secrets
from collections.abc import AsyncGenerator
from contextlib import ExitStack, aclosing
from dataclasses import dataclass
from pathlib import Path

import aiofiles
from fastapi import HTTPException

from ..background_tasks import TaskProgress, TaskType
from ..background_tasks.manager import BackgroundTaskManager
from ..minecraft import DockerMCManager
from ..operation_admission import get_server_write_admission
from ..operations.context import record_phase
from ..operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from ..operations.execution import settle_before_release
from ..operations.finalization import finalize
from ..operations.journal_types import OperationState
from ..runtime_resources import current_runtime
from ..world.artifacts import artifact_root, reap_restore_stages, release_artifact
from ..world.locks import ServerOperationLock
from ..world.preview_rendering import WorldPreviewRenderer
from ..world.scope_execution import RestoreScopeExecutor
from .file_restore import FileRestoreAdapter
from .preparation import PreparedSnapshot, SnapshotPlanner
from .preview_actions import MAX_ACTION_BYTES, MAX_LINE_BYTES, read_actions
from .preview_models import PreviewAction, PreviewActions, PreviewBinding, PreviewResult
from .preview_sessions import PreviewSessionManager
from .preview_version import target_version
from .restoration_store import SessionFactory
from .scopes import GlobalScope, ResolvedScope, SnapshotScope, WorldScope
from .service import SnapshotService


@dataclass
class PreviewPreparation:
    preview_id: str | None = None


class SnapshotPreviews:
    def __init__(
        self,
        snapshots: SnapshotService,
        manager: DockerMCManager,
        lock: ServerOperationLock,
        tasks: BackgroundTaskManager,
        sessions: SessionFactory,
        root: Path,
        base_dir: Path | None = None,
    ) -> None:
        self._snapshots = snapshots
        self._tasks = tasks
        self._sessions = sessions
        self._planner = SnapshotPlanner(
            snapshots, FileRestoreAdapter(manager, lock), sessions, root
        )
        self.manager = PreviewSessionManager(
            base_dir or artifact_root("restore"), snapshots.repository_use
        )
        self._renderer = WorldPreviewRenderer(
            snapshots, RestoreScopeExecutor(snapshots), self.manager
        )
        self._active: dict[str, ResolvedScope] = {}

    async def prepare(self) -> None:
        await self.manager.reap_orphan_dirs()
        await reap_restore_stages()

    def start_janitor(self):
        return self.manager.start_janitor()

    async def close(self, *, preserve_artifacts: bool = False) -> None:
        await self.manager.close(preserve_artifacts=preserve_artifacts)

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
                        "message": "快照预览仍在准备，请等待完成或停止准备后再删除服务器",
                    },
                )

    async def submit(self, scope: SnapshotScope, source_id: str, actor_id: int) -> dict:
        task_id = secrets.token_hex(16)
        preparation = PreviewPreparation()
        with ExitStack() as stack:
            stack.enter_context(self._snapshots.repository_use.retain([source_id]))
            prepared = await self._planner.prepare(scope)
            admission = get_server_write_admission()
            stack.enter_context(
                admission.write_global()
                if isinstance(scope, GlobalScope)
                else admission.write(
                    [ref.server_id for ref in prepared.resolved.servers]
                )
            )
            self._active[task_id] = prepared.resolved
            stack.callback(self._active.pop, task_id, None)
            claims = (
                tuple(
                    ResourceClaim(ResourceKind.MAP_CACHE, ref.server_id)
                    for ref in prepared.resolved.servers
                )
                if isinstance(scope, WorldScope)
                else ()
            )
            submitted = await self._tasks.submit_durable(
                TaskType.SNAPSHOT_PREVIEW,
                "准备快照恢复预览",
                self._prepare(prepared, source_id, claims, preparation),
                actor_id=actor_id,
                task_id=task_id,
                server_id=None if isinstance(scope, GlobalScope) else scope.server_id,
                server_refs=prepared.resolved.servers,
                claims=claims,
                require_existing_targets=not isinstance(scope, GlobalScope),
                exclusive_key=f"snapshot-preview:{'global' if isinstance(scope, GlobalScope) else scope.server_id}",
                on_finished=lambda state: self._finish(preparation, state),
            )
            retained = stack.pop_all()
            submitted.awaitable.add_done_callback(lambda _: retained.close())
        return {"task_id": task_id}

    async def _finish(
        self, preparation: PreviewPreparation, state: OperationState
    ) -> None:
        if state is not OperationState.SUCCEEDED and preparation.preview_id:
            await self.manager.end_and_wait(preparation.preview_id)

    async def _prepare(
        self,
        prepared: PreparedSnapshot,
        source_id: str,
        claims: tuple[ResourceClaim, ...],
        preparation: PreviewPreparation,
    ) -> AsyncGenerator[TaskProgress]:
        yield TaskProgress(message="正在检查预览范围和源快照")
        async with get_operation_coordinator().acquire(claims), settle_before_release():
            await self._planner.revalidate(prepared)
            source = await self._snapshots.get_snapshot(source_id)
            prepared, _ = await self._planner.with_source(prepared, source)
            scope = prepared.resolved.scope
            version = await target_version(prepared.resolved, self._sessions)
            selection = scope.selection if isinstance(scope, WorldScope) else None
            affected = (
                len({(x // 32, z // 32) for x, z in selection.chunks})
                if selection and selection.chunks
                else len(selection.regions)
                if selection
                else 0
            )
            directory = await self.manager.create_session(
                None if isinstance(scope, GlobalScope) else scope.server_id,
                server_ids=tuple(ref.server_id for ref in prepared.resolved.servers),
                server_generation=prepared.resolved.servers[0].generation
                if isinstance(scope, WorldScope)
                else None,
                affected_regions=affected,
                source_snapshot_id=source_id,
            )
            preview_id, ready = directory.name, False
            preparation.preview_id = preview_id
            try:
                async with self.manager.use(preview_id) as session:
                    await record_phase("preparing_preview")
                    yield TaskProgress(
                        message="正在准备恢复预览", result={"preview_id": preview_id}
                    )
                    counts = {"updated": 0, "deleted": 0, "restored": 0}
                    if selection:
                        async with aclosing(
                            self._renderer.prepare(
                                session_id=preview_id,
                                data_path=prepared.resolved.servers[0].data_path,
                                source_snapshot_id=source_id,
                                selection=selection,
                                paths=prepared.paths,
                                protection=prepared.protection,
                            )
                        ) as events:
                            async for event in events:
                                self.manager.heartbeat(preview_id)
                                yield event
                    else:
                        size = 0
                        async with (
                            aiofiles.open(directory / "actions.jsonl", "wb") as output,
                            aclosing(
                                self._snapshots.restore(
                                    source_id,
                                    prepared.paths,
                                    dry_run=True,
                                    protection=prepared.protection,
                                )
                            ) as events,
                        ):
                            async for event in events:
                                self.manager.heartbeat(preview_id)
                                if event.kind == "status":
                                    yield TaskProgress(
                                        message="正在比较文件变更",
                                        progress=event.percent_done * 100
                                        if event.percent_done is not None
                                        else None,
                                    )
                                if (
                                    event.kind != "file"
                                    or event.action
                                    not in ("updated", "deleted", "restored")
                                    or not event.item
                                ):
                                    continue
                                action = PreviewAction(
                                    action=event.action,
                                    item=event.item,
                                    size=event.size,
                                )
                                line = (action.model_dump_json() + "\n").encode()
                                size += len(line)
                                if (
                                    size > MAX_ACTION_BYTES
                                    or len(line) > MAX_LINE_BYTES
                                ):
                                    raise HTTPException(
                                        status_code=400,
                                        detail="预览明细过大，请缩小选择范围",
                                    )
                                await output.write(line)
                                counts[event.action] += 1
                    await self._planner.revalidate(prepared)
                    self.manager.heartbeat(preview_id)
                    if (
                        await target_version(prepared.resolved, self._sessions)
                        != version
                    ):
                        raise HTTPException(
                            status_code=409, detail="预览准备期间目标已变化，请重新预览"
                        )
                    skipped = prepared.protection.skipped_under(prepared.resolved.paths)
                    result = PreviewResult(
                        preview_id=preview_id,
                        kind="map" if selection else "files",
                        preview_summary="地图预览已就绪"
                        if selection
                        else f"{counts['updated']} 项更新，{counts['deleted']} 项删除，{counts['restored']} 项恢复",
                        updated=counts["updated"],
                        deleted=counts["deleted"],
                        restored=counts["restored"],
                        skipped_paths=[str(path) for path in skipped[:100]],
                        skipped_count=len(skipped),
                    )
                    session.binding = PreviewBinding(source_id, prepared, version)
                    session.result = result
                    ready = True
                    yield TaskProgress(
                        progress=100,
                        message="预览已就绪",
                        result=result.model_dump(mode="json"),
                    )
            finally:

                async def cleanup() -> None:
                    await release_artifact("world_preview", preview_id)
                    session = self.manager.get_session(preview_id)
                    if not ready or session is None:
                        await self.manager.end(preview_id)

                await finalize(cleanup())

    async def get(self, preview_id: str) -> PreviewResult:
        async with self.manager.use(preview_id) as session:
            if session.result is None or session.binding is None:
                raise HTTPException(status_code=409, detail="预览尚未准备完成")
            await self._planner.revalidate(session.binding.prepared)
            return session.result

    async def validate(
        self, preview_id: str, prepared: PreparedSnapshot, source_id: str
    ) -> PreviewBinding:
        async with self.manager.use(preview_id) as session:
            binding = session.binding
            if binding is None or session.result is None:
                raise HTTPException(status_code=409, detail="预览尚未准备完成")
            await self.validate_binding(binding, prepared, source_id)
            return binding

    async def validate_binding(
        self, binding: PreviewBinding, prepared: PreparedSnapshot, source_id: str
    ) -> None:
        if (
            binding.source_id != source_id
            or binding.prepared.resolved != prepared.resolved
            or binding.prepared.protection.current != prepared.protection.current
        ):
            raise HTTPException(
                status_code=409, detail="预览与源快照、目标或保护规则不一致，请重新预览"
            )
        if (
            await target_version(prepared.resolved, self._sessions)
            != binding.target_version
        ):
            raise HTTPException(
                status_code=409, detail="预览后的目标已变化，请重新预览"
            )

    async def actions(self, preview_id: str, cursor: int, limit: int) -> PreviewActions:
        await self.get(preview_id)
        async with self.manager.use(preview_id) as session:
            if session.result is None or session.result.kind != "files":
                raise HTTPException(status_code=400, detail="此预览使用地图展示")
            return await read_actions(session.base_dir / "actions.jsonl", cursor, limit)

    async def tile(self, preview_id: str, rx: int, rz: int) -> bytes:
        await self.get(preview_id)
        return await self._renderer.read_preview_tile(preview_id, rx, rz)

    async def heartbeat(self, preview_id: str) -> None:
        await self.get(preview_id)

    async def end(self, preview_id: str, actor_id: int) -> dict:
        # Closing is allowed even after a target was replaced or removed.
        session = self.manager.get_session(preview_id)
        if session is not None and session.binding is None:
            raise HTTPException(
                status_code=409, detail="请通过任务停止尚未完成的预览准备"
            )
        submitted = await self._tasks.submit_durable(
            TaskType.SNAPSHOT_PREVIEW_CLEANUP,
            "清理快照预览",
            self._cleanup(preview_id),
            actor_id=actor_id,
            exclusive_key=f"snapshot-preview-cleanup:{preview_id}",
        )
        return {"task_id": submitted.task_id}

    async def _cleanup(self, preview_id: str) -> AsyncGenerator[TaskProgress]:
        yield TaskProgress(message="正在等待预览读取与渲染结束")
        await record_phase("cleaning_preview")
        await finalize(self.manager.end_and_wait(preview_id))
        yield TaskProgress(
            progress=100,
            message="预览临时数据已清理",
            result={"preview_id": preview_id},
        )


def get_snapshot_previews() -> SnapshotPreviews | None:
    return current_runtime().snapshot_previews
