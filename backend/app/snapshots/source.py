"""Snapshot metadata compiled for logical protection and coverage checks."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from functools import cached_property
from pathlib import Path

from fastapi import HTTPException

from ..utils import async_fs
from .coverage import PathIndex
from .evidence import snapshot_absence, snapshot_selection
from .models import ResticSnapshot
from .protection import SnapshotProtection

PathResolver = Callable[[Sequence[Path]], Awaitable[tuple[Path, ...]]]


class SnapshotSource:
    def __init__(self, snapshot: ResticSnapshot, *, apply_exclusions: bool = True) -> None:
        self.snapshot = snapshot
        self.paths = tuple(Path(value) for value in snapshot.paths)
        self.excludes = tuple(Path(value) for value in snapshot.excludes) if apply_exclusions else ()
        self.roots = PathIndex(self.paths)
        self.excluded = PathIndex(self.excludes)
        self.selection = snapshot_selection(snapshot) if apply_exclusions else None
        self._root_set = frozenset(self.paths)

    @cached_property
    def absence(self) -> PathIndex:
        return PathIndex(snapshot_absence(self.snapshot))

    def execution_path(self, logical: Path, execution: Path) -> Path:
        if self.selection is None:
            return execution
        mapping = self.selection.mapping_for(logical)
        if mapping is not None:
            mapped = mapping.execution_path(logical)
            if self.roots.contains(mapped):
                return mapped
        return logical if logical in self._root_set else execution

    def covers(self, path: Path, protection: SnapshotProtection) -> bool:
        actual = self.execution_path(path, protection.execution_path(path))
        return (
            protection.permits(path)
            and not self.excluded.contains(actual)
            and self.roots.contains(actual)
        )

    async def protect(
        self,
        protection: SnapshotProtection,
        *,
        resolve: PathResolver = async_fs.resolve_many,
    ) -> SnapshotProtection:
        if not protection.apply_exclusions:
            return protection
        excluded = set(protection.excluded)
        if self.selection is not None:
            excluded.update(self.selection.excluded)
            selected_roots: set[Path] = set()
            for index, item in enumerate(protection.mappings):
                if index % 256 == 0:
                    await asyncio.sleep(0)
                selected_roots.update(self.roots.ancestors(item.logical))
            roots = tuple(sorted(selected_roots))
            executions = await resolve(roots)
            if executions != roots:
                self._reject_changed_source()
        if not protection.mappings:
            excluded.update(self.excludes)
        for index, mapping in enumerate(protection.mappings):
            if index % 256 == 0:
                await asyncio.sleep(0)
            actual = self.execution_path(mapping.logical, mapping.execution)
            if actual != mapping.execution:
                self._reject_changed_source()
            if self.excluded.contains(actual):
                excluded.add(mapping.logical)
            excluded.update(
                mapping.logical / path.relative_to(actual)
                for path in self.excluded.descendants(actual)
            )
        return SnapshotProtection.capture(
            protection.current,
            tuple(excluded),
            data_paths=protection.data_paths,
            mappings=protection.mappings,
        )

    @staticmethod
    def _reject_changed_source() -> None:
        raise HTTPException(
            status_code=409, detail="源快照对应的链接目标已变化，请重新选择范围"
        )
