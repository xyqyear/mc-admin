"""Snapshot path-coverage predicate, shared by service and self-check.

A snapshot "covers" a target path when one of its recorded paths is an
ancestor of (or equal to) the target and none of its recorded excludes is.
An exclude strictly below the target does not disqualify: restoring the
directory is still meaningful, and excluded content is protected separately
at restore time. Excludes are literal absolute paths (the ignore config
bans globs), so pure path math is sound.
"""

from collections.abc import Iterable
from pathlib import Path


def covers(
    target: Path,
    resolved_paths: Iterable[Path],
    resolved_excludes: Iterable[Path],
) -> bool:
    if any(target.is_relative_to(exclude) for exclude in resolved_excludes):
        return False
    return any(target.is_relative_to(path) for path in resolved_paths)
