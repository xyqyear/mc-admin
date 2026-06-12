"""Unit tests for restore planning against a fake snapshot tree."""

from pathlib import Path

import pytest

from app.snapshots.models import NodeKind
from app.snapshots.planner import (
    DirStep,
    FileStep,
    RestorePlan,
    TargetIgnoredError,
    build_restore_plan,
)

SNAP = "abc123"


class FakeClient:
    """ls() answers from a canned snapshot tree of absolute paths."""

    def __init__(self, tree: dict[str, NodeKind]):
        self._tree = {Path(p): kind for p, kind in tree.items()}
        self.ls_calls: list[Path] = []

    async def ls(self, snapshot_id: str, path: Path) -> dict[Path, NodeKind]:
        self.ls_calls.append(path)
        if path not in self._tree:
            return {}
        nodes = {path: self._tree[path]}
        for candidate, kind in self._tree.items():
            if candidate.parent == path:
                nodes[candidate] = kind
        return nodes


@pytest.fixture
def client():
    return FakeClient(
        {
            "/srv": NodeKind.DIR,
            "/srv/x": NodeKind.DIR,
            "/srv/x/data": NodeKind.DIR,
            "/srv/x/data/server.properties": NodeKind.FILE,
            "/srv/x/data/world": NodeKind.DIR,
            "/srv/x/data/world/region": NodeKind.DIR,
            "/srv/x/data/world/region/r.0.0.mca": NodeKind.FILE,
            "/srv/x/data/world/region/r.0.1.mca": NodeKind.FILE,
        }
    )


async def test_single_dir_target(client):
    plan = await build_restore_plan(client, SNAP, [Path("/srv/x")], [])
    assert plan.steps == (DirStep(source_dir=Path("/srv/x"), excludes=()),)


async def test_dir_target_with_ignores_under_it(client):
    ignored = [Path("/srv/x/data/.mcmap"), Path("/srv/x/data/logs")]
    plan = await build_restore_plan(client, SNAP, [Path("/srv/x")], ignored)
    assert plan.steps == (
        DirStep(
            source_dir=Path("/srv/x"),
            excludes=("/data/.mcmap", "/data/logs"),
        ),
    )


async def test_ignore_outside_target_not_translated(client):
    ignored = [Path("/srv/y/data/.mcmap")]
    plan = await build_restore_plan(client, SNAP, [Path("/srv/x")], ignored)
    assert plan.steps == (DirStep(source_dir=Path("/srv/x"), excludes=()),)


async def test_file_targets_grouped_by_parent(client):
    targets = [
        Path("/srv/x/data/world/region/r.0.1.mca"),
        Path("/srv/x/data/world/region/r.0.0.mca"),
    ]
    plan = await build_restore_plan(client, SNAP, targets, [])
    assert plan.steps == (
        FileStep(
            source_dir=Path("/srv/x/data/world/region"),
            includes=("/r.0.0.mca", "/r.0.1.mca"),
        ),
    )


async def test_missing_file_with_present_parent_is_included(client):
    # On disk but absent from the snapshot: restic deletes it via the include.
    targets = [Path("/srv/x/data/world/region/r.9.9.mca")]
    plan = await build_restore_plan(client, SNAP, targets, [])
    assert plan.steps == (
        FileStep(
            source_dir=Path("/srv/x/data/world/region"),
            includes=("/r.9.9.mca",),
        ),
    )


async def test_missing_parent_skips_group(client):
    targets = [Path("/srv/x/data/world/entities/r.0.0.mca")]
    plan = await build_restore_plan(client, SNAP, targets, [])
    assert plan.steps == ()


async def test_mixed_dir_and_file_targets(client):
    targets = [
        Path("/srv/x/data/world/region/r.0.0.mca"),
        Path("/srv/x/data/server.properties"),
        Path("/srv/x/data/world/entities/r.0.0.mca"),  # parent missing → skipped
    ]
    plan = await build_restore_plan(client, SNAP, targets, [])
    assert plan.steps == (
        FileStep(source_dir=Path("/srv/x/data"), includes=("/server.properties",)),
        FileStep(
            source_dir=Path("/srv/x/data/world/region"), includes=("/r.0.0.mca",)
        ),
    )


async def test_dir_steps_ordered_before_file_steps(client):
    targets = [
        Path("/srv/x/data/world/region/r.0.0.mca"),
        Path("/srv/x/data/world"),
    ]
    with pytest.raises(ValueError, match="disjoint"):
        # world contains region/r.0.0.mca → overlap is rejected, not reordered
        await build_restore_plan(client, SNAP, targets, [])


async def test_disjoint_dir_and_file_steps_order(client):
    targets = [
        Path("/srv/x/data/server.properties"),
        Path("/srv/x/data/world"),
    ]
    plan = await build_restore_plan(client, SNAP, targets, [])
    assert plan.steps == (
        DirStep(source_dir=Path("/srv/x/data/world"), excludes=()),
        FileStep(source_dir=Path("/srv/x/data"), includes=("/server.properties",)),
    )


async def test_ignored_target_raises(client):
    with pytest.raises(TargetIgnoredError):
        await build_restore_plan(
            client, SNAP, [Path("/srv/x/data/.mcmap")], [Path("/srv/x/data/.mcmap")]
        )


async def test_target_under_ignored_dir_raises(client):
    with pytest.raises(TargetIgnoredError):
        await build_restore_plan(
            client,
            SNAP,
            [Path("/srv/x/data/.mcmap/tiles/r.0.0.png")],
            [Path("/srv/x/data/.mcmap")],
        )


async def test_relative_target_rejected(client):
    with pytest.raises(ValueError, match="absolute"):
        await build_restore_plan(client, SNAP, [Path("relative/path")], [])


async def test_duplicate_targets_deduplicated(client):
    targets = [Path("/srv/x"), Path("/srv/x")]
    plan = await build_restore_plan(client, SNAP, targets, [])
    assert plan.steps == (DirStep(source_dir=Path("/srv/x"), excludes=()),)


async def test_one_ls_probe_per_unique_parent(client):
    region = Path("/srv/x/data/world/region")
    targets = [region / f"r.{i}.{j}.mca" for i in range(20) for j in range(20)]
    targets += [region / f"c.{i}.{j}.mcc" for i in range(20) for j in range(20)]
    plan = await build_restore_plan(client, SNAP, targets, [])
    assert client.ls_calls == [region]
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert isinstance(step, FileStep)
    assert len(step.includes) == 800


async def test_stage_target_mirrors_absolute_path():
    step = DirStep(source_dir=Path("/srv/x/data/world"), excludes=())
    assert RestorePlan.stage_target(Path("/tmp/stage"), step) == Path(
        "/tmp/stage/srv/x/data/world"
    )
