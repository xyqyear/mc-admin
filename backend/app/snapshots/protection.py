import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from .ignores import is_ignored
from .planner import TargetIgnoredError


@dataclass(frozen=True)
class SnapshotProtection:
    current: tuple[Path, ...]
    excluded: tuple[Path, ...]

    @property
    def version(self) -> str:
        value = json.dumps([str(path) for path in self.current], separators=(",", ":"))
        return hashlib.sha256(value.encode()).hexdigest()

    def permits(self, path: Path) -> bool:
        return not is_ignored(path, self.excluded)

    def require_targets(self, paths: Sequence[Path]) -> None:
        if not paths:
            raise TargetIgnoredError("所选范围没有可处理的内容")
        for path in paths:
            if not self.permits(path):
                raise TargetIgnoredError(f"此路径已被快照规则忽略: {path}")

    def skipped_under(self, paths: Sequence[Path]) -> tuple[Path, ...]:
        return tuple(
            path
            for path in self.excluded
            if any(path.is_relative_to(target) for target in paths)
        )

    def require_current(self, current: Sequence[Path]) -> None:
        if self.current != tuple(sorted(set(current))):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "snapshot_rules_changed",
                    "message": "快照忽略规则或世界路径已变化，请重新确认操作",
                },
            )

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "current": [str(path) for path in self.current],
                "excluded": [str(path) for path in self.excluded],
            }
        )

    @classmethod
    def capture(
        cls, current: Sequence[Path], retained: Sequence[Path] = ()
    ) -> "SnapshotProtection":
        return cls(
            tuple(sorted(set(current))), tuple(sorted(set(current) | set(retained)))
        )
