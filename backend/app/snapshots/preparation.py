"""Resolve snapshot targets and protection before preview or mutation."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from fastapi import HTTPException

from ..files.resources import path_claims
from ..operations.context import revalidate_targets
from ..operations.coordinator import ResourceClaim, ResourceKind
from ..utils import async_fs
from ..world.scope_execution import RestoreScopeExecutor
from ..world.selection import group_chunks_by_region
from .evidence import snapshot_absence
from .file_restore import FileRestoreAdapter
from .models import ResticSnapshot
from .protection import SnapshotProtection
from .restoration_models import RestorationType
from .restoration_store import SessionFactory
from .scopes import (
    GlobalScope,
    ResolvedScope,
    ServerScope,
    SnapshotScope,
    WorldScope,
    resolve_scope,
)
from .service import SnapshotService


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

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(
            path for path in self.resolved.paths if self.protection.permits(path)
        )


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
        protection = await self.snapshots.protection(
            retained=retained,
            data_paths=[ref.data_path for ref in resolved.servers],
        )
        protection = protection.with_mappings(resolved.mappings)
        protection.require_targets(
            [path for path in resolved.paths if protection.permits(path)]
            if isinstance(scope, WorldScope)
            else resolved.paths
        )
        maintenance = (
            tuple(ref.server_id for ref in resolved.servers)
            if not restoring
            or isinstance(scope, (GlobalScope, ServerScope, WorldScope))
            else tuple(await self._files.maintenance_servers(resolved.execution_paths))
        )
        claims = set(resolved.claims)
        missing_parents: set[Path] = set()
        existing_parents: dict[Path, bool] = {}
        for path in resolved.execution_paths:
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
        protection = await self.snapshots.with_source_protection(
            prepared.protection, source
        )
        documented_absence = snapshot_absence(source)
        absent = tuple(
            set(absent)
            | {
                path
                for path in prepared.resolved.paths
                if any(path.is_relative_to(parent) for parent in documented_absence)
            }
        )
        if selection:
            covered = {
                path
                for path in prepared.paths
                if path.suffix != ".mcc"
                and (
                    path in absent
                    or any(
                        protection.execution_path(path).is_relative_to(parent)
                        for parent in absent_parents
                    )
                    or self.snapshots.source_covers(source, path, protection)
                )
            }
            if not covered:
                raise HTTPException(status_code=400, detail="源快照未覆盖所选范围")
            uncovered = {
                path
                for path in prepared.paths
                if path.suffix != ".mcc" and path not in covered
            }
            uncovered_dirs = {
                path.parent for path in uncovered if path.suffix == ".mca"
            }
            covered_dirs = {path.parent for path in covered if path.suffix == ".mca"}
            uncovered_dirs -= covered_dirs
            uncovered = {
                path for path in uncovered if path.parent not in uncovered_dirs
            } | uncovered_dirs
            for path in prepared.paths:
                if path.suffix == ".mcc":
                    _, x, z, _ = path.name.split(".")
                    region = path.with_name(f"r.{int(x) // 32}.{int(z) // 32}.mca")
                    if region in uncovered:
                        uncovered.add(path)
            if uncovered:
                protection = SnapshotProtection.capture(
                    protection.current,
                    [*protection.excluded, *uncovered],
                    data_paths=protection.data_paths,
                    mappings=protection.mappings,
                )
        prepared = replace(prepared, protection=protection)
        protection.require_targets(
            prepared.paths if selection else prepared.resolved.paths
        )
        await self.require_permitted_chunks(prepared.resolved, protection)
        for path in prepared.paths:
            if selection and path.suffix == ".mcc":
                continue
            if (
                path not in absent
                and not any(
                    protection.execution_path(path).is_relative_to(parent)
                    for parent in absent_parents
                )
                and not self.snapshots.source_covers(source, path, protection)
            ):
                raise HTTPException(status_code=400, detail="源快照未覆盖所选范围")
        return prepared, absent

    @staticmethod
    async def require_permitted_chunks(
        resolved: ResolvedScope, protection: SnapshotProtection
    ) -> None:
        scope = resolved.scope
        if (
            isinstance(scope, WorldScope)
            and scope.selection.type is RestorationType.CHUNKS
        ):
            selection = scope.selection
            permitted_chunks = False
            for (rx, rz), chunks in group_chunks_by_region(selection.chunks).items():
                for path in resolved.paths:
                    if (
                        path.name == f"r.{rx}.{rz}.mca"
                        and await RestoreScopeExecutor.allowed_chunks(
                            resolved.servers[0].data_path,
                            path,
                            rx,
                            rz,
                            chunks,
                            protection,
                        )
                    ):
                        permitted_chunks = True
            if not permitted_chunks:
                protection.require_targets([])
