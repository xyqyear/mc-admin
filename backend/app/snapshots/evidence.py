import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

from ..errors import PublicOperationError
from .models import ResticSnapshot
from .path_mapping import (
    SnapshotPathMapping,
    compact_mappings,
    mapping_json,
    mappings_from_json,
)

_ABSENCE_TAG = "mc-admin-absence-v1:"
_SELECTION_TAG = "mc-admin-logical-v2:"


@dataclass(frozen=True)
class SnapshotSelection:
    mappings: tuple[SnapshotPathMapping, ...]
    excluded: tuple[Path, ...]

    @cached_property
    def mapping_index(self) -> dict[Path, SnapshotPathMapping]:
        return {item.logical: item for item in self.mappings}

    def mapping_for(self, path: Path) -> SnapshotPathMapping | None:
        if not self.mappings:
            return None
        if path in self.mapping_index:
            return self.mapping_index[path]
        for parent in path.parents:
            if parent in self.mapping_index:
                return self.mapping_index[parent]
        return None


def selection_tags(
    mappings: Sequence[SnapshotPathMapping], excluded: Sequence[Path]
) -> list[str]:
    value = json.dumps(
        {
            "mappings": mapping_json(
                compact_mappings(
                    [item for item in mappings if item.logical != item.execution]
                )
            ),
            "excluded": [str(path) for path in sorted(set(excluded))],
        },
        separators=(",", ":"),
    ).encode()
    tag = _SELECTION_TAG + base64.urlsafe_b64encode(value).decode()
    if len(tag) > 32768:
        raise PublicOperationError("快照逻辑路径记录过大，请缩小选择范围")
    return [tag]


def snapshot_selection(snapshot: ResticSnapshot) -> SnapshotSelection | None:
    tags = [tag for tag in snapshot.tags if tag.startswith(_SELECTION_TAG)]
    if not tags:
        return None
    if len(tags) != 1:
        raise PublicOperationError("快照逻辑路径记录无效，未执行恢复")
    return _decode_selection(tags[0])


@lru_cache(maxsize=128)
def _decode_selection(tag: str) -> SnapshotSelection:
    try:
        if len(tag) > 32768:
            raise ValueError("Invalid selection metadata size")
        value = json.loads(
            base64.b64decode(tag[len(_SELECTION_TAG) :], altchars=b"-_", validate=True)
        )
        if not isinstance(value, dict) or set(value) != {"mappings", "excluded"}:
            raise ValueError("Invalid logical selection")
        paths = value["excluded"]
        if not isinstance(paths, list) or not all(
            isinstance(path, str)
            and Path(path).is_absolute()
            and ".." not in Path(path).parts
            for path in paths
        ):
            raise ValueError("Invalid logical exclusions")
        return SnapshotSelection(
            mappings_from_json(value["mappings"]), tuple(Path(path) for path in paths)
        )
    except (ValueError, TypeError, binascii.Error) as error:
        raise PublicOperationError("快照逻辑路径记录无效，未执行恢复") from error


def snapshot_source_path(
    snapshot: ResticSnapshot, logical: Path, execution: Path
) -> Path:
    selection = snapshot_selection(snapshot)
    if selection is None:
        return execution
    roots = _snapshot_roots(tuple(snapshot.paths))
    mapping = selection.mapping_for(logical)
    if mapping is not None:
        mapped = mapping.execution_path(logical)
        if mapped in roots or any(parent in roots for parent in mapped.parents):
            return mapped
    if logical in roots:
        return logical
    return execution


@lru_cache(maxsize=128)
def _snapshot_roots(paths: tuple[str, ...]) -> frozenset[Path]:
    return frozenset(Path(path) for path in paths)


def absence_tags(paths: Sequence[Path]) -> list[str]:
    if not paths:
        return []
    value = json.dumps([str(path) for path in paths], separators=(",", ":")).encode()
    tag = _ABSENCE_TAG + base64.urlsafe_b64encode(value).decode()
    if len(tag) > 32768:
        raise PublicOperationError("快照缺失目录记录过大，请缩小选择范围")
    return [tag]


def snapshot_absence(snapshot: ResticSnapshot) -> tuple[Path, ...]:
    tags = [tag for tag in snapshot.tags if tag.startswith(_ABSENCE_TAG)]
    if not tags:
        return ()
    try:
        if len(tags) != 1 or len(tags[0]) > 32768:
            raise ValueError("Invalid absence metadata size")
        values = json.loads(
            base64.b64decode(
                tags[0][len(_ABSENCE_TAG) :], altchars=b"-_", validate=True
            )
        )
        if not isinstance(values, list) or not all(
            isinstance(value, str)
            and Path(value).is_absolute()
            and ".." not in Path(value).parts
            for value in values
        ):
            raise ValueError("Invalid absence paths")
        return tuple(Path(value) for value in values)
    except (ValueError, binascii.Error) as error:
        raise PublicOperationError("快照缺失目录记录无效，未执行恢复") from error
