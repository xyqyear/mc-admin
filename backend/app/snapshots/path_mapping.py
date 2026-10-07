from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SnapshotPathMapping:
    logical: Path
    execution: Path

    def execution_path(self, path: Path) -> Path:
        if path == self.logical:
            return self.execution
        return self.execution / path.relative_to(self.logical)

    def logical_path(self, path: Path) -> Path:
        if path == self.execution:
            return self.logical
        return self.logical / path.relative_to(self.execution)


def mapping_json(mappings: Sequence[SnapshotPathMapping]) -> list[dict[str, str]]:
    return [
        {"logical": str(item.logical), "execution": str(item.execution)}
        for item in mappings
    ]


def execution_parent_mappings(
    parents: Sequence[Path], mappings: Sequence[SnapshotPathMapping]
) -> tuple[SnapshotPathMapping, ...]:
    result = set()
    for parent in parents:
        for item in mappings:
            if not item.execution.is_relative_to(parent):
                continue
            logical = item.logical
            for _ in item.execution.relative_to(parent).parts:
                logical = logical.parent
            result.add(SnapshotPathMapping(logical, parent))
    return tuple(
        sorted(result, key=lambda item: (str(item.execution), str(item.logical)))
    )


def compact_mappings(
    mappings: Sequence[SnapshotPathMapping],
) -> tuple[SnapshotPathMapping, ...]:
    result = set(mappings)
    while True:
        groups: dict[SnapshotPathMapping, list[SnapshotPathMapping]] = {}
        for item in result:
            if (
                item.logical.name == item.execution.name
                and item.logical.parent != item.logical
            ):
                parent = SnapshotPathMapping(item.logical.parent, item.execution.parent)
                groups.setdefault(parent, []).append(item)
        shared = [
            parent
            for parent, children in groups.items()
            if len(children) > 1
            and sum(other.logical == parent.logical for other in groups) == 1
        ]
        if not shared:
            return tuple(sorted(result, key=lambda item: str(item.logical)))
        for parent in shared:
            result.difference_update(groups[parent])
            result.add(parent)


def mappings_from_json(values: object) -> tuple[SnapshotPathMapping, ...]:
    if not isinstance(values, list):
        raise TypeError("Invalid path mappings")
    result = []
    for value in values:
        if not isinstance(value, dict) or set(value) != {"logical", "execution"}:
            raise ValueError("Invalid path mapping")
        for path in value.values():
            if (
                not isinstance(path, str)
                or not Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                raise ValueError("Invalid mapped path")
        result.append(
            SnapshotPathMapping(Path(value["logical"]), Path(value["execution"]))
        )
    if len({item.logical for item in result}) != len(result):
        raise ValueError("Duplicate logical path mapping")
    return tuple(result)
