"""Backup application ownership around the existing Restic coverage rules."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from aiofiles import os as aioos
from fastapi import HTTPException

from ..files.resources import path_claims, require_same_claims
from ..minecraft import DockerMCManager
from ..operations.context import record_phase
from ..operations.coordinator import (
    ConflictPolicy,
    ResourceClaim,
    ResourceKind,
    ResourceLease,
)
from ..operations.execution import operation_scope, settle_before_release
from ..utils import async_fs
from .models import ResticSnapshotWithSummary
from .service import SnapshotService

if TYPE_CHECKING:
    from ..world.locks import ServerOperationLock


class SnapshotMaintenanceConflict(Exception):
    pass


async def resolve_backup_paths(manager: DockerMCManager, root: Path, server_id: str | None, paths: list[str] | None) -> list[Path]:
    if not server_id and not paths:
        return [await async_fs.resolve(root)]
    if not server_id:
        raise HTTPException(status_code=400, detail="Cannot specify paths without server_id")
    instance = manager.get_instance(server_id)
    try:
        project = await async_fs.resolve_inside(root, instance.get_project_path())
        if not paths:
            return [project]
        data = instance.get_data_path()
        return [await async_fs.resolve_inside(data, data / path.lstrip("/")) for path in paths]
    except async_fs.PathOutsideBaseError as error:
        raise HTTPException(status_code=400, detail="路径越界：目标路径不在服务器目录内") from error


async def snapshot_claims(manager: DockerMCManager, paths: Sequence[Path]) -> tuple[ResourceClaim, ...]:
    targets = [await async_fs.resolve(path) for path in paths]
    claims: set[ResourceClaim] = set()
    manager_root = getattr(manager, "servers_path", None)
    if isinstance(manager_root, Path):
        root = await async_fs.resolve(manager_root)
        if any(root.is_relative_to(target) for target in targets):
            claims.add(ResourceClaim(ResourceKind.FILES))
    for instance in await manager.get_all_instances():
        project = await async_fs.resolve(instance.get_project_path())
        scoped = [project if project.is_relative_to(target) else target for target in targets if target.is_relative_to(project) or project.is_relative_to(target)]
        claims.update(await path_claims(project, scoped, server_id=instance.get_name()))
    return tuple(sorted(claims))


class SnapshotApplication:
    def __init__(self, snapshots: SnapshotService, manager: DockerMCManager, lock: "ServerOperationLock") -> None:
        self.snapshots = snapshots
        self.manager = manager
        self.lock = lock

    async def backup(
        self, paths: Sequence[Path], *, actor_id: int | None = None,
        parent: ResourceLease | None = None, allow_missing: bool = False,
    ) -> ResticSnapshotWithSummary:
        from ..world.locks import LockHolder, ServerOperationKind

        present = [await aioos.path.exists(path) for path in paths]
        for path, exists in zip(paths, present, strict=True):
            if not exists and not allow_missing:
                raise HTTPException(status_code=404, detail=f"Path not found: {path}")
        if not any(present):
            raise HTTPException(status_code=404, detail="备份目标路径不存在")
        claims = await snapshot_claims(self.manager, paths)
        server_ids = sorted({claim.server_id for claim in claims if claim.server_id})
        maintenance = server_ids if parent is None else [server_id for server_id in server_ids if any(claim.kind == ResourceKind.MAINTENANCE and claim.server_id == server_id for claim in parent.claims)]
        holder = LockHolder(ServerOperationKind.BACKUP, datetime.now(UTC), actor_id, "快照备份")
        async with (
            operation_scope("snapshot_backup", server_ids, actor_id=actor_id, claims=claims),
            self.lock.lease(maintenance, holder, claims=claims, policy=ConflictPolicy.SKIP, parent=parent) as lease,
        ):
            if lease is None:
                raise SnapshotMaintenanceConflict("服务器正在维护")
            async with settle_before_release():
                require_same_claims(claims, await snapshot_claims(self.manager, paths))
                await record_phase("creating_snapshot")
                snapshot = await self.snapshots.create_snapshot(paths)
                await record_phase("snapshot_created")
                return snapshot
