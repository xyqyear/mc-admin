"""Resolve snapshot targets and protection before preview or mutation."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import Path

from fastapi import HTTPException

from ..files.resources import path_claims
from ..operations.context import revalidate_targets
from ..operations.coordinator import ResourceClaim, ResourceKind
from ..utils import async_fs
from ..world.selection import resolve_paths
from .evidence import snapshot_absence
from .file_restore import FileRestoreAdapter
from .models import ResticSnapshot
from .protection import SnapshotProtection
from .restoration_store import SessionFactory
from .scopes import (
    GlobalScope,
    PathsScope,
    ResolvedScope,
    ServerScope,
    SnapshotScope,
    WorldScope,
    resolve_scope,
)
from .service import SnapshotService
from .source import SnapshotSource


@dataclass(frozen=True)
class PreparedSnapshot:
    resolved: ResolvedScope
    protection: SnapshotProtection
    maintenance: tuple[str, ...]
    claims: tuple[ResourceClaim, ...]
    missing_parents: tuple[Path, ...]
    history_paths: tuple[Path, ...] | None = None
    from_history: bool = False
    legacy_world: bool = False

    @cached_property
    def paths(self) -> tuple[Path, ...]:
        return self.protection.select_targets(self.resolved.paths)


class SnapshotPlanner:
    def __init__(
        self,
        snapshots: SnapshotService,
        files: FileRestoreAdapter,
        sessions: SessionFactory,
        root: Path,
    ) -> None:
        self.snapshots = snapshots
        self._files = files
        self._sessions = sessions
        self._root = root

    async def prepare(
        self,
        scope: SnapshotScope,
        *,
        restoring: bool = False,
        retained: Sequence[Path] = (),
        history_paths: tuple[Path, ...] | None = None,
        from_history: bool = False,
        legacy_world: bool = False,
    ) -> PreparedSnapshot:
        resolved = await resolve_scope(
            scope,
            root=self._root,
            sessions=self._sessions,
            history_paths=history_paths,
            allow_missing_dimension=from_history,
        )
        if isinstance(scope, WorldScope):
            protection = SnapshotProtection.world()
        else:
            protection = await self.snapshots.protection(
                retained=retained,
                data_paths=[ref.data_path for ref in resolved.servers],
            )
        protection = protection.with_mappings(resolved.mappings)
        paths = protection.select_targets(resolved.paths)
        executions = tuple(protection.execution_path(path) for path in paths)
        maintenance = (
            tuple(ref.server_id for ref in resolved.servers)
            if not restoring
            or isinstance(scope, (GlobalScope, ServerScope, WorldScope))
            else tuple(await self._files.maintenance_servers(executions))
        )
        claims = set(resolved.claims)
        missing_parents: set[Path] = set()
        existing_parents: dict[Path, bool] = {}
        for path in executions:
            for parent in path.parents:
                if not parent.is_relative_to(self._root):
                    break
                if parent not in existing_parents:
                    existing_parents[parent] = await async_fs.lexists(parent)
                if existing_parents[parent]:
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
            history_paths,
            from_history,
            legacy_world,
        )

    async def file_admission(
        self, prepared: PreparedSnapshot, source_id: str
    ) -> PreparedSnapshot:
        if not isinstance(prepared.resolved.scope, PathsScope) or not prepared.maintenance:
            return prepared
        # Source exclusions can remove the world roots that require a stopped server.
        source = await self.snapshots.get_snapshot(source_id)
        protection = await SnapshotSource(source).protect(prepared.protection)
        paths = protection.select_targets(prepared.resolved.paths)
        maintenance = await self._files.maintenance_servers(
            [protection.execution_path(path) for path in paths]
        )
        return replace(prepared, protection=protection, maintenance=tuple(maintenance))

    async def revalidate(self, prepared: PreparedSnapshot) -> None:
        await revalidate_targets()
        current = await resolve_scope(
            prepared.resolved.scope,
            root=self._root,
            sessions=self._sessions,
            history_paths=prepared.history_paths,
            allow_missing_dimension=prepared.from_history,
        )
        if current != prepared.resolved:
            raise HTTPException(
                status_code=409, detail="目标路径或服务器实例已变化，请重新确认操作"
            )
        await self.snapshots.revalidate_protection(prepared.protection)

    async def with_source(
        self,
        prepared: PreparedSnapshot,
        source: ResticSnapshot,
        absent: tuple[Path, ...] = (),
        absent_parents: tuple[Path, ...] = (),
    ) -> tuple[PreparedSnapshot, tuple[Path, ...]]:
        scope = prepared.resolved.scope
        selection = scope.selection if isinstance(scope, WorldScope) else None
        source_index = SnapshotSource(source, apply_exclusions=prepared.protection.apply_exclusions)
        protection = await source_index.protect(prepared.protection)
        documented_absence = snapshot_absence(source)
        absent = tuple(
            set(absent)
            | {
                path
                for path in prepared.resolved.paths
                if any(path.is_relative_to(parent) for parent in documented_absence)
            }
        )
        prepared = replace(prepared, protection=protection)
        protection.select_targets(prepared.resolved.paths)
        coverage_paths = prepared.paths
        if selection and not prepared.from_history:
            coverage_paths = tuple(await resolve_paths(
                prepared.resolved.servers[0].data_path, selection, include_mcc=False,
            ))
        for path in coverage_paths:
            if selection and path.suffix == ".mcc":
                continue
            if (
                path not in absent
                and not any(
                    protection.execution_path(path).is_relative_to(parent)
                    for parent in absent_parents
                )
                and not source_index.covers(path, protection)
            ):
                raise HTTPException(status_code=400, detail="源快照未覆盖所选范围")
        return prepared, absent
