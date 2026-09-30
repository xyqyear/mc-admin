"""Stopped-world checks and cache cleanup for file restoration."""

from collections.abc import Sequence
from pathlib import Path

from ..minecraft import DockerMCManager, MCServerStatus
from ..operations.context import (
    current_execution,
    mark_cache_degraded,
)
from ..servers.references import ServerRef
from ..utils import async_fs
from ..world import png_invalidate
from ..world.locks import ServerOperationLock
from ..world.maintenance import affected_servers
from .application import (
    SnapshotMaintenanceConflict,
)


class SnapshotServerRunning(Exception):
    pass


class FileRestoreAdapter:
    def __init__(
        self,
        manager: DockerMCManager,
        operation_lock: ServerOperationLock,
    ) -> None:
        self._manager = manager
        self._lock = operation_lock

    async def maintenance_servers(self, paths: Sequence[Path]) -> list[str]:
        return await affected_servers(self._manager, paths, world_only=True)

    async def check_available(self, server_ids: list[str]) -> None:
        for server_id in server_ids:
            if self._lock.is_locked(server_id):
                raise SnapshotMaintenanceConflict(f"服务器 '{server_id}' 正在维护")
        await self.check_stopped(server_ids)

    async def check_stopped(self, server_ids: list[str]) -> None:
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

    async def invalidate(
        self, items: list[str], servers: Sequence[ServerRef], uncertain_servers: Sequence[str] = ()
    ) -> None:
        if not items and not uncertain_servers:
            return
        execution = current_execution()
        if execution is not None:
            record = await execution.journal.get(execution.operation_id)
            if record is not None and (record.processes or not record.ownership_known):
                for server in execution.servers:
                    await mark_cache_degraded(server.server_id)
                return
        for server in servers:
            if server.server_id in uncertain_servers:
                try:
                    tiles = server.data_path / ".mcmap" / "tiles"
                    await async_fs.resolve_inside(server.data_path, tiles)
                    try:
                        await async_fs.rmtree(tiles)
                    except FileNotFoundError:
                        pass
                except Exception:
                    await mark_cache_degraded(server.server_id)
                    raise
                continue
            pngs = png_invalidate.pngs_for_restic_items(server.data_path, items)
            if pngs:
                try:
                    await png_invalidate.delete_pngs(
                        pngs, data_path=server.data_path
                    )
                except Exception:
                    await mark_cache_degraded(server.server_id)
                    raise
