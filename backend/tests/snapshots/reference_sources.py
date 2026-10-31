"""Exhaustive pre-refactor rules used only for differential regression evidence."""

from pathlib import Path

from fastapi import HTTPException

from app.snapshots.api_models import SnapshotRestoreSource
from app.snapshots.evidence import snapshot_absence, snapshot_selection
from app.snapshots.protection import SnapshotProtection
from app.utils import async_fs


def source_path(snapshot, logical, execution):
    selection = snapshot_selection(snapshot)
    if selection is None:
        return execution
    roots = {Path(value) for value in snapshot.paths}
    mapping = selection.mapping_for(logical)
    if mapping is not None:
        mapped = mapping.execution_path(logical)
        if any(mapped.is_relative_to(root) for root in roots):
            return mapped
    return logical if logical in roots else execution


async def protect(protection, snapshot):
    excluded = list(protection.excluded)
    selection = snapshot_selection(snapshot)
    if selection is not None:
        excluded.extend(selection.excluded)
        roots = {Path(value) for value in snapshot.paths}
        selected = {
            parent for item in protection.mappings
            for parent in (item.logical, *item.logical.parents) if parent in roots
        }
        roots = tuple(sorted(selected))
        if await async_fs.resolve_many(roots) != roots:
            raise HTTPException(409)
    if not protection.mappings:
        excluded.extend(Path(value) for value in snapshot.excludes)
    for mapping in protection.mappings:
        actual = source_path(snapshot, mapping.logical, mapping.execution)
        if actual != mapping.execution:
            raise HTTPException(409)
        for value in snapshot.excludes:
            path = Path(value)
            if actual.is_relative_to(path):
                excluded.append(mapping.logical)
            elif path.is_relative_to(actual):
                excluded.append(mapping.logical / path.relative_to(actual))
    return SnapshotProtection.capture(
        protection.current, excluded, data_paths=protection.data_paths,
        mappings=protection.mappings,
    )


async def select_sources(resolved, protection, paths, sources):
    results = []
    for snapshot in sources:
        try:
            protected = await protect(protection, snapshot)
        except HTTPException as error:
            if error.status_code == 409:
                continue
            raise
        allowed = [path for path in paths if not any(path.is_relative_to(p) for p in protected.excluded)]
        if not allowed:
            continue
        absent = snapshot_absence(snapshot)
        roots = [Path(value) for value in snapshot.paths]
        excluded = [Path(value) for value in snapshot.excludes]
        def covered(path, absent=absent, snapshot=snapshot, protected=protected, excluded=excluded, roots=roots):
            if any(path.is_relative_to(parent) for parent in absent):
                return True
            actual = source_path(snapshot, path, protected.execution_path(path))
            return not any(actual.is_relative_to(p) for p in excluded) and any(actual.is_relative_to(p) for p in roots)
        if all(covered(path) for path in allowed):
            exact_targets = set(resolved.paths)
            skipped = [
                path for path in protected.excluded
                if path in exact_targets or any(path.is_relative_to(target) or target.is_relative_to(path) for target in resolved.paths)
            ]
            results.append(SnapshotRestoreSource(
                **snapshot.model_dump(), skipped_paths=[str(path) for path in skipped[:100]],
                skipped_count=len(skipped),
            ))
    return results
