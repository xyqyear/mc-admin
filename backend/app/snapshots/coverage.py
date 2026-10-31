"""Snapshot path-coverage predicate, shared by service and self-check.

A snapshot "covers" a target path when one of its recorded paths is an
ancestor of (or equal to) the target and none of its recorded excludes is.
An exclude strictly below the target does not disqualify: restoring the
directory is still meaningful, and excluded content is protected separately
at restore time. Excludes are literal absolute paths (the ignore config
bans globs), so pure path math is sound.
"""

from bisect import bisect_left
from collections.abc import Iterable, Iterator
from pathlib import Path


class PathIndex:
    def __init__(self, paths: Iterable[Path]) -> None:
        self._paths = {path.parts: path for path in paths}
        self._keys = sorted(self._paths)

    def ancestors(self, path: Path) -> Iterator[Path]:
        parts = path.parts
        minimum = 1 if path.anchor else 0
        for length in range(len(parts), minimum - 1, -1):
            if (parent := self._paths.get(parts[:length])) is not None:
                yield parent

    def contains(self, path: Path) -> bool:
        return next(self.ancestors(path), None) is not None

    def descendants(self, path: Path) -> Iterator[Path]:
        parts = path.parts
        start = bisect_left(self._keys, parts)
        for index in range(start, len(self._keys)):
            key = self._keys[index]
            if key[:len(parts)] != parts:
                break
            candidate = self._paths[key]
            if candidate.anchor == path.anchor:
                yield candidate

    def overlaps(self, path: Path) -> bool:
        return self.contains(path) or next(self.descendants(path), None) is not None


def covers(
    target: Path,
    resolved_paths: Iterable[Path],
    resolved_excludes: Iterable[Path],
) -> bool:
    if any(target.is_relative_to(exclude) for exclude in resolved_excludes):
        return False
    return any(target.is_relative_to(path) for path in resolved_paths)
