"""Restore selection safety, external listing budget and real restore outcomes."""

from pathlib import Path

import pytest

from app.snapshots.models import NodeKind
from app.snapshots.planner import (
    FileStep,
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


async def test_overlapping_targets_are_rejected(client):
    targets = [
        Path("/srv/x/data/world/region/r.0.0.mca"),
        Path("/srv/x/data/world"),
    ]
    with pytest.raises(ValueError, match="disjoint"):
        # world contains region/r.0.0.mca → overlap is rejected, not reordered
        await build_restore_plan(client, SNAP, targets, [])


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


@pytest.mark.binary("restic")
async def test_mixed_and_duplicate_selections_restore_only_allowed_bytes(case):
    world = case.data / "world"
    world.mkdir()
    terrain = world / "region.dat"
    protected = world / "keep.txt"
    config = case.data / "config.txt"
    unselected = case.data / "unselected.txt"
    for path in (terrain, protected, config, unselected):
        path.write_text("snapshot " + path.name)
    case.config.snapshots.ignored_paths = ["world/keep.txt", "other-server/cache"]
    snapshot = await case.snapshots.create_snapshot([case.data])
    for path in (terrain, protected, config, unselected):
        path.write_text("live " + path.name)
    targets = [config, world, config]
    preview = [event async for event in case.snapshots.restore(snapshot.id, targets, dry_run=True)]
    assert preview
    assert all(path.read_text() == "live " + path.name for path in (terrain, protected, config, unselected))

    results = [event async for event in case.snapshots.restore(snapshot.id, targets)]
    assert results
    assert terrain.read_text() == "snapshot region.dat"
    assert config.read_text() == "snapshot config.txt"
    assert protected.read_text() == "live keep.txt"
    assert unselected.read_text() == "live unselected.txt"
