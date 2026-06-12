"""Ignore-path resolution and restic pattern translation.

Ignored paths come from ``config.snapshots.ignored_paths`` — literal paths
relative to each server's data directory, with ``<LEVEL_NAME>`` segments
expanding to the ``level-name`` from that server's ``server.properties``.
Backup excludes them; restore neither overwrites nor deletes them.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import Protocol

from ..dynamic_config.configs.snapshots import LEVEL_NAME_TOKEN
from ..minecraft.properties import read_level_name
from ..utils import async_fs


class ServerInstance(Protocol):
    def get_data_path(self) -> Path: ...


class InstanceProvider(Protocol):
    """The slice of ``DockerMCManager`` the snapshots package needs."""

    async def get_all_instances(self) -> Sequence[ServerInstance]: ...


async def resolve_server_ignores(
    data_path: Path, patterns: Sequence[str]
) -> list[Path]:
    """Expand config patterns into absolute ignored paths for one server.

    Reads ``server.properties`` at most once, and only when a pattern
    actually uses the ``<LEVEL_NAME>`` token.
    """
    level_name: str | None = None
    resolved: list[Path] = []
    for raw in patterns:
        parts = PurePosixPath(raw).parts
        if LEVEL_NAME_TOKEN in parts:
            if level_name is None:
                level_name = await read_level_name(data_path)
            parts = tuple(
                level_name if part == LEVEL_NAME_TOKEN else part for part in parts
            )
        resolved.append(await async_fs.resolve(data_path.joinpath(*parts)))
    return resolved


async def resolve_all_ignores(
    manager: InstanceProvider, patterns: Sequence[str]
) -> list[Path]:
    """Absolute ignored paths across every known server instance."""
    if not patterns:
        return []
    ignored: list[Path] = []
    for instance in await manager.get_all_instances():
        ignored.extend(
            await resolve_server_ignores(instance.get_data_path(), patterns)
        )
    return ignored


def is_ignored(path: Path, ignored: Iterable[Path]) -> bool:
    """True if ``path`` equals or lies under any ignored path."""
    return any(path.is_relative_to(i) for i in ignored)


def subtree_excludes(subtree_root: Path, ignored: Iterable[Path]) -> list[str]:
    """Subtree-relative ``--exclude`` patterns for ignored paths under ``subtree_root``.

    Restic matches restore patterns against paths relative to the restore
    subtree, so each pattern is anchored with a leading ``/``.
    """
    patterns: list[str] = []
    for i in ignored:
        if i != subtree_root and i.is_relative_to(subtree_root):
            patterns.append("/" + i.relative_to(subtree_root).as_posix())
    return patterns


def backup_excludes(
    backup_paths: Sequence[Path], ignored: Iterable[Path]
) -> list[str]:
    """Absolute ``--exclude`` patterns for ignored paths under any backup path."""
    return [
        str(i)
        for i in ignored
        if any(i.is_relative_to(p) for p in backup_paths)
    ]
