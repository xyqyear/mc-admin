"""Read-only candidate coverage with request-local reuse."""

import asyncio
from collections.abc import Sequence
from pathlib import Path

from fastapi import HTTPException

from ..utils import async_fs
from ..world.selection import resolve_paths
from .api_models import SnapshotRestoreSource
from .evidence import snapshot_absence
from .models import ResticSnapshot
from .planner import TargetIgnoredError
from .protection import SnapshotProtection
from .restoration_store import SessionFactory
from .scopes import ResolvedScope, SnapshotScope, WorldScope, resolve_scope
from .service import SnapshotService
from .source import SnapshotSource


class QueryBindings:
    def __init__(self) -> None:
        self._resolved: dict[Path, Path] = {}

    async def resolve(self, paths: Sequence[Path]) -> tuple[Path, ...]:
        missing = tuple(path for path in paths if path not in self._resolved)
        if missing:
            actual = await async_fs.resolve_many(missing)
            self._resolved.update(zip(missing, actual, strict=True))
        return tuple(self._resolved[path] for path in paths)


async def eligible_snapshots(
    scope: SnapshotScope,
    *,
    snapshots: SnapshotService,
    root: Path,
    sessions: SessionFactory,
) -> list[SnapshotRestoreSource]:
    resolved = await resolve_scope(scope, root=root, sessions=sessions, include_mcc=False)
    if isinstance(scope, WorldScope):
        protection = SnapshotProtection.world()
    else:
        protection = await snapshots.protection(
            data_paths=[ref.data_path for ref in resolved.servers]
        )
    protection = protection.with_mappings(resolved.mappings)
    paths = resolved.paths
    if isinstance(scope, WorldScope):
        paths = tuple(await resolve_paths(
            resolved.servers[0].data_path, scope.selection, include_mcc=False
        ))
    paths = protection.select_targets(paths)
    return await select_sources(resolved, protection, paths, await snapshots.list_snapshots())


async def select_sources(
    resolved: ResolvedScope,
    protection: SnapshotProtection,
    paths: Sequence[Path],
    sources: Sequence[ResticSnapshot],
) -> list[SnapshotRestoreSource]:
    world = isinstance(resolved.scope, WorldScope)
    if world:
        protection = SnapshotProtection.world(resolved.mappings)
    bindings = QueryBindings()
    decisions: dict[tuple[object, ...], tuple[tuple[str, ...], int] | None] = {}
    eligible = []
    for snapshot in sources:
        await asyncio.sleep(0)
        key = (
            (tuple(snapshot.paths), snapshot_absence(snapshot)) if world else
            (tuple(snapshot.paths), tuple(snapshot.excludes), tuple(snapshot.tags))
        )
        if key not in decisions:
            source = SnapshotSource(snapshot, apply_exclusions=not world)
            decisions[key] = await _source_details(source, protection, paths, resolved.paths, bindings)
        details = decisions[key]
        if details is not None:
            skipped_paths, count = details
            eligible.append(SnapshotRestoreSource(
                **snapshot.model_dump(), skipped_paths=list(skipped_paths), skipped_count=count,
            ))
    return eligible


async def _source_details(
    source: SnapshotSource,
    protection: SnapshotProtection,
    paths: Sequence[Path],
    targets: Sequence[Path],
    bindings: QueryBindings,
) -> tuple[tuple[str, ...], int] | None:
    try:
        protection = await source.protect(protection, resolve=bindings.resolve)
        allowed = protection.select_targets(paths)
    except HTTPException as error:
        if error.status_code == 409:
            return None
        raise
    except TargetIgnoredError:
        return None
    for index, path in enumerate(allowed):
        if index % 256 == 0:
            await asyncio.sleep(0)
        if not source.absence.contains(path) and not source.covers(path, protection):
            return None
    skipped = protection.skipped_under(targets)
    return tuple(str(path) for path in skipped[:100]), len(skipped)
