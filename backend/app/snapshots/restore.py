"""Application flow for restoring file paths and server snapshots."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path

from anyio import CancelScope

from ..minecraft import DockerMCManager, MCServerStatus
from ..world import png_invalidate
from ..world.locks import LockHolder, ServerOperationKind, ServerOperationLock
from ..world.maintenance import affected_servers
from .service import SnapshotService


class SnapshotMaintenanceConflict(Exception):
    pass


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
        async with self._lock.try_acquire_servers(server_ids, holder) as acquired:
            if not acquired:
                raise SnapshotMaintenanceConflict("服务器正在维护")
            await self._check_stopped(server_ids)
            yield {"event_type": "start", "message": f"正在恢复快照 {snapshot_id[:8]}"}
            yield {"event_type": "safety_snapshot", "message": "正在创建安全快照"}
            safety = await self._snapshots.create_snapshot(paths)
            yield {
                "event_type": "safety_snapshot",
                "safety_snapshot_id": safety.id,
                "message": f"安全快照 {safety.short_id}",
            }
            touched: list[str] = []
            try:
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
            finally:
                with CancelScope(shield=True):
                    await self._invalidate(touched)
            yield {"event_type": "invalidate_cache", "message": "地图缓存已失效"}
            yield {
                "event_type": "complete",
                "safety_snapshot_id": safety.id,
                "message": f"快照 {snapshot_id[:8]} 恢复完成",
            }

    async def _invalidate(self, items: list[str]) -> None:
        if not items:
            return
        for instance in await self._manager.get_all_instances():
            pngs = png_invalidate.pngs_for_restic_items(instance.get_data_path(), items)
            if pngs:
                await png_invalidate.delete_pngs(pngs)
