"""Restore planning: targets + ignored paths → one restic invocation per step.

Restic cannot combine ``--include`` with ``--exclude``, so the planner splits
intent into two step shapes:

- ``DirStep`` — subtree restore of a directory present in the snapshot, with
  subtree-relative excludes protecting ignored paths from ``--delete``.
- ``FileStep`` — subtree restore of a parent directory with file includes;
  ``--delete`` then only considers the included names, deleting on-disk files
  the snapshot lacks (speculative includes of nonexistent paths are no-ops).

Targets whose parent directory is absent from the snapshot are skipped:
restic can neither restore them nor traverse-delete them there.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .ignores import is_ignored, subtree_excludes
from .models import NodeKind


class SnapshotTreeReader(Protocol):
    """The slice of ``ResticClient`` the planner needs."""

    async def ls(self, snapshot_id: str, path: Path) -> dict[Path, NodeKind]: ...


class TargetIgnoredError(ValueError):
    """A restore target equals or lies under an ignored path."""


@dataclass(frozen=True)
class DirStep:
    source_dir: Path
    excludes: tuple[str, ...]


@dataclass(frozen=True)
class FileStep:
    source_dir: Path
    includes: tuple[str, ...]


RestoreStep = DirStep | FileStep


@dataclass(frozen=True)
class RestorePlan:
    snapshot_id: str
    steps: tuple[RestoreStep, ...]

    @staticmethod
    def stage_target(stage_root: Path, step: RestoreStep) -> Path:
        """Staged restores mirror the full absolute path under ``stage_root``."""
        return stage_root / step.source_dir.relative_to("/")


def _check_no_nested_targets(targets: Sequence[Path]) -> None:
    target_set = set(targets)
    for target in targets:
        for ancestor in target.parents:
            if ancestor in target_set:
                raise ValueError(
                    f"Restore targets must be disjoint: {target} lies under {ancestor}"
                )


async def build_restore_plan(
    client: SnapshotTreeReader,
    snapshot_id: str,
    targets: Sequence[Path],
    ignored: Sequence[Path],
) -> RestorePlan:
    """Classify targets against the snapshot tree and emit ordered steps.

    Probes one ``restic ls`` per unique parent directory, so thousands of
    file targets sharing a few parents (regions/chunks restores) stay cheap.
    """
    unique_targets = sorted(set(targets))
    for target in unique_targets:
        if not target.is_absolute():
            raise ValueError(f"Restore target must be absolute: {target}")
        if is_ignored(target, ignored):
            raise TargetIgnoredError(
                f"目标路径在忽略列表中，无法恢复: {target}"
            )
    _check_no_nested_targets(unique_targets)

    by_parent: dict[Path, list[Path]] = {}
    for target in unique_targets:
        by_parent.setdefault(target.parent, []).append(target)

    dir_targets: list[Path] = []
    file_groups: dict[Path, list[str]] = {}
    for parent in sorted(by_parent):
        nodes = await client.ls(snapshot_id, parent)
        if not nodes:
            continue
        for target in by_parent[parent]:
            if nodes.get(target) is NodeKind.DIR:
                dir_targets.append(target)
            else:
                file_groups.setdefault(parent, []).append(target.name)

    steps: list[RestoreStep] = [
        DirStep(
            source_dir=target,
            excludes=tuple(subtree_excludes(target, ignored)),
        )
        for target in sorted(dir_targets)
    ]
    steps.extend(
        FileStep(
            source_dir=parent,
            includes=tuple(f"/{name}" for name in sorted(names)),
        )
        for parent, names in sorted(file_groups.items())
    )
    return RestorePlan(snapshot_id=snapshot_id, steps=tuple(steps))
