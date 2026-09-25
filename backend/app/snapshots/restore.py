"""Application flow for restoring file paths and server snapshots."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path

from ..files.resources import path_claims, require_same_claims
from ..minecraft import DockerMCManager, MCServerStatus
from ..operation_admission import get_server_write_admission
from ..operations.context import (
    current_execution,
    mark_cache_degraded,
    record_phase,
    retain_recovery_reference,
)
from ..operations.coordinator import ConflictPolicy, ResourceClaim, ResourceKind
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from ..utils import async_fs
from ..world import png_invalidate
from ..world.locks import LockHolder, ServerOperationKind, ServerOperationLock
from ..world.maintenance import affected_servers
from .application import (
    SnapshotApplication,
    SnapshotMaintenanceConflict,
    snapshot_claims,
)
from .service import SnapshotService


class SnapshotServerRunning(Exception):
    pass


class SnapshotRestoreService:
    def __init__(
        self,
        snapshots: SnapshotService,
        manager: DockerMCManager,
        operation_lock: ServerOperationLock,
    ) -> None:
        self._snapshots = snapshots
        self._manager = manager
        self._lock = operation_lock

    async def maintenance_servers(self, paths: Sequence[Path]) -> list[str]:
        return await affected_servers(self._manager, paths, world_only=True)

    async def check_available(self, server_ids: list[str]) -> None:
        for server_id in server_ids:
            if self._lock.is_locked(server_id):
                raise SnapshotMaintenanceConflict(f"服务器 '{server_id}' 正在维护")
        await self._check_stopped(server_ids)

    async def _check_stopped(self, server_ids: list[str]) -> None:
        for server_id in server_ids:
            status = await self._manager.get_instance(server_id).get_status()
            if status in (
                MCServerStatus.RUNNING,
                MCServerStatus.HEALTHY,
                MCServerStatus.STARTING,
            ):
                raise SnapshotServerRunning(
                    f"请先停止服务器 '{server_id}' 再恢复世界或整个服务器"
                )

    async def restore(
        self, snapshot_id: str, paths: list[Path], server_ids: list[str], user_id: int
    ) -> AsyncGenerator[dict]:
        holder = LockHolder(
            kind=ServerOperationKind.RESTORE,
            started_at=datetime.now(UTC),
            user_id=user_id,
            description="快照恢复",
        )
        affected = await affected_servers(self._manager, paths, world_only=False)
        async def files_with_cache():
            files = list(await snapshot_claims(self._manager, paths))
            for server_id in server_ids:
                instance = self._manager.get_instance(server_id)
                files.extend(await path_claims(instance.get_project_path(), [instance.get_data_path() / ".mcmap" / "tiles"], server_id=server_id))
            return tuple(sorted(set(files)))

        files = await files_with_cache()
        claims = (*files, *(ResourceClaim(ResourceKind.MAP_CACHE, server_id) for server_id in server_ids))
        with get_server_write_admission().write(affected):
            async with (
                operation_scope("snapshot_restore", affected, actor_id=user_id, claims=claims),
                self._lock.lease(server_ids, holder, claims=claims, policy=ConflictPolicy.SKIP) as lease,
                settle_before_release(),
            ):
                if lease is None:
                    raise SnapshotMaintenanceConflict("服务器正在维护")
                require_same_claims(files, await files_with_cache())
                await self._check_stopped(server_ids)
                yield {"event_type": "start", "message": f"正在恢复快照 {snapshot_id[:8]}"}
                yield {"event_type": "safety_snapshot", "message": "正在创建安全快照"}
                safety = await SnapshotApplication(self._snapshots, self._manager, self._lock).backup(paths, actor_id=user_id, parent=lease)
                await retain_recovery_reference("safety_snapshot", safety.id)
                yield {
                    "event_type": "safety_snapshot",
                    "safety_snapshot_id": safety.id,
                    "message": f"安全快照 {safety.short_id}",
                }
                touched: list[str] = []
                restored = False
                try:
                    await record_phase("restoring_files", changed=True)
                    yield {"event_type": "restore", "percent": 0.0}
                    async with aclosing(
                        self._snapshots.restore(snapshot_id, paths)
                    ) as events:
                        async for event in events:
                            if event.kind == "status" and event.percent_done is not None:
                                yield {
                                    "event_type": "restore",
                                    "percent": event.percent_done * 100,
                                }
                            elif (
                                event.kind == "file"
                                and event.action in ("updated", "restored", "deleted")
                                and event.item
                            ):
                                touched.append(event.item)
                    restored = True
                finally:
                    await finalize(self._invalidate(touched, [] if restored else server_ids))
                yield {"event_type": "invalidate_cache", "message": "地图缓存已失效"}
                yield {
                    "event_type": "complete",
                    "safety_snapshot_id": safety.id,
                    "message": f"快照 {snapshot_id[:8]} 恢复完成",
                }

    async def _invalidate(self, items: list[str], uncertain_servers: Sequence[str] = ()) -> None:
        if not items and not uncertain_servers:
            return
        execution = current_execution()
        if execution is not None:
            record = await execution.journal.get(execution.operation_id)
            if record is not None and (record.processes or not record.ownership_known):
                for server in execution.servers:
                    await mark_cache_degraded(server.server_id)
                return
        for instance in await self._manager.get_all_instances():
            if instance.get_name() in uncertain_servers:
                try:
                    tiles = instance.get_data_path() / ".mcmap" / "tiles"
                    await async_fs.resolve_inside(instance.get_data_path(), tiles)
                    try:
                        await async_fs.rmtree(tiles)
                    except FileNotFoundError:
                        pass
                except Exception:
                    await mark_cache_degraded(instance.get_name())
                    raise
                continue
            pngs = png_invalidate.pngs_for_restic_items(instance.get_data_path(), items)
            if pngs:
                try:
                    await png_invalidate.delete_pngs(pngs, data_path=instance.get_data_path())
                except Exception:
                    await mark_cache_degraded(instance.get_name())
                    raise
