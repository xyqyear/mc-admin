"""Read-only candidate discovery with compact external-chunk selection."""

import asyncio
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

from fastapi import HTTPException

from ..utils import async_fs
from ..world.region_files import parse_region_filename
from ..world.selection import resolve_paths
from .api_models import SnapshotRestoreSource
from .models import ResticSnapshot
from .path_mapping import SnapshotPathMapping
from .planner import TargetIgnoredError
from .protection import SnapshotProtection
from .restoration_models import RestorationType
from .restoration_store import SessionFactory
from .scopes import ResolvedScope, SnapshotScope, WorldScope, resolve_scope
from .service import SnapshotService
from .source import SnapshotSource

_MCC_NAME = re.compile(r"c\.(-?\d+)\.(-?\d+)\.mcc")


class RegionSidecars:
    def __init__(self, resolved: ResolvedScope) -> None:
        self.directories: dict[Path, Path] = {}
        self.regions: dict[Path, set[tuple[int, int]]] = {}
        if not isinstance(resolved.scope, WorldScope) or resolved.scope.selection.type not in {
            RestorationType.REGIONS, RestorationType.CHUNKS,
        }:
            return
        for mapping in resolved.mappings:
            if (coords := parse_region_filename(mapping.logical.name)) is not None:
                directory = mapping.logical.parent
                self.directories[directory] = mapping.execution.parent
                self.regions.setdefault(directory, set()).add(coords)

    def related(self, path: Path, *, expand_parent: bool = False) -> Iterator[Path]:
        for directory, regions in self.regions.items():
            if path != directory and path.is_relative_to(directory):
                name = path.relative_to(directory).parts[0]
                match = _MCC_NAME.fullmatch(name)
                if match is not None:
                    x, z = map(int, match.groups())
                    if (x // 32, z // 32) in regions and name == f"c.{x}.{z}.mcc":
                        yield directory / name
            elif expand_parent and directory.is_relative_to(path):
                for rx, rz in regions:
                    for x in range(rx * 32, (rx + 1) * 32):
                        for z in range(rz * 32, (rz + 1) * 32):
                            yield directory / f"c.{x}.{z}.mcc"

    def exceptions(self, source: SnapshotSource, protection: SnapshotProtection) -> Iterator[Path]:
        for path in protection.excluded:
            yield from self.related(path)
        if source.selection is not None:
            for path in source.selection.excluded:
                yield from self.related(path)
            for mapping in source.selection.mappings:
                yield from self.related(mapping.logical)
            for path in source.paths:
                yield from self.related(path)
        for directory, execution in self.directories.items():
            for path in source.excludes:
                if execution.is_relative_to(path):
                    yield from self.related(directory, expand_parent=True)
                elif path.is_relative_to(execution):
                    yield from self.related(directory / path.relative_to(execution))

    def binding(self, path: Path) -> SnapshotPathMapping:
        # World sidecars are regular files; the directory binding owns their location.
        return SnapshotPathMapping(path, self.directories[path.parent] / path.name)


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
    protection = (await snapshots.protection(
        data_paths=[ref.data_path for ref in resolved.servers]
    )).with_mappings(resolved.mappings)
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
    query = CandidateQuery(resolved, protection, paths)
    eligible: list[SnapshotRestoreSource] = []
    for snapshot in sources:
        await asyncio.sleep(0)
        details = await query.skips(snapshot)
        if details is not None:
            skipped_paths, count = details
            eligible.append(SnapshotRestoreSource(
                **snapshot.model_dump(), skipped_paths=list(skipped_paths), skipped_count=count,
            ))
    return eligible


class CandidateQuery:
    def __init__(self, resolved: ResolvedScope, protection: SnapshotProtection, paths: Sequence[Path]) -> None:
        self.resolved = resolved
        self.protection = protection
        self.paths = paths
        self.sidecars = RegionSidecars(resolved)
        self.bindings = QueryBindings()
        self._decisions: dict[
            tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
            tuple[tuple[str, ...], int] | None,
        ] = {}

    async def skips(self, snapshot: ResticSnapshot) -> tuple[tuple[str, ...], int] | None:
        key = (tuple(snapshot.paths), tuple(snapshot.excludes), tuple(snapshot.tags))
        if key not in self._decisions:
            self._decisions[key] = await self._evaluate(SnapshotSource(snapshot))
        return self._decisions[key]

    async def _evaluate(self, source: SnapshotSource) -> tuple[tuple[str, ...], int] | None:
        extra: set[Path] = set()
        for index, path in enumerate(self.sidecars.exceptions(source, self.protection)):
            if index % 256 == 0:
                await asyncio.sleep(0)
            extra.add(path)
        mappings = (*self.resolved.mappings, *(self.sidecars.binding(path) for path in sorted(extra)))
        try:
            protected = await source.protect(
                self.protection.with_mappings(mappings), resolve=self.bindings.resolve
            )
        except HTTPException as error:
            if error.status_code == 409:
                return None
            raise
        try:
            allowed = protected.select_targets(self.paths)
        except TargetIgnoredError:
            return None
        if all(source.absence.contains(path) or source.covers(path, protected) for path in allowed):
            skipped = protected.skipped_under((*self.resolved.paths, *extra))
            return tuple(str(path) for path in skipped[:100]), len(skipped)
        return None
