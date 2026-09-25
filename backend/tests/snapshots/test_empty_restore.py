import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.snapshots import ResticClient, SnapshotService
from app.snapshots import service as service_module
from app.snapshots.planner import EmptyStep
from app.utils import async_fs
from app.utils.exec import exec_command
from tests.support.runtime import set_runtime_resource

pytestmark = pytest.mark.binary("restic")


class Instance:
    def __init__(self, data: Path) -> None:
        self.data = data

    def get_data_path(self) -> Path:
        return self.data


class Manager:
    def __init__(self, data: Path) -> None:
        self.instance = Instance(data)

    async def get_all_instances(self) -> list[Instance]:
        return [self.instance]


@pytest.fixture
async def empty_snapshot(tmp_path, monkeypatch):
    data = tmp_path / "server" / "data"
    region = data / "world" / "region"
    region.mkdir(parents=True)
    (data / "world" / "level.dat").write_bytes(b"level")
    client = ResticClient(str(tmp_path / "repository"), password="temporary-test")
    await exec_command(str(client.binary_path), "init", env=client.env)
    configuration = SimpleNamespace(snapshots=SimpleNamespace(ignored_paths=[]))
    set_runtime_resource(monkeypatch, 'dynamic_configuration', configuration)
    service = SnapshotService(client, Manager(data))
    snapshot = await service.create_snapshot([data / "world"])
    return SimpleNamespace(data=data, region=region, client=client, service=service, snapshot=snapshot, config=configuration)


@pytest.mark.parametrize("scope", ["directory", "file"])
async def test_empty_snapshot_removes_only_selected_live_content(empty_snapshot, scope):
    app = empty_snapshot
    selected = app.region / "r.0.0.mca"
    sibling = app.region / "r.1.0.mca"
    selected.write_bytes(b"selected")
    sibling.write_bytes(b"sibling")
    targets = [app.region] if scope == "directory" else [selected]
    plan = await app.service.build_plan(app.snapshot.id, targets)
    assert len(plan.steps) == 1 and isinstance(plan.steps[0], EmptyStep)
    events = [event async for event in app.service.restore(app.snapshot.id, targets)]
    assert not selected.exists()
    assert sibling.exists() == (scope == "file")
    assert app.region.is_dir()
    expected = {str(selected)} if scope == "file" else {str(selected), str(sibling)}
    assert {event.item for event in events if event.action == "deleted"} == expected
    assert events[-1].files_deleted == len(expected)


async def test_empty_directory_preserves_current_and_snapshot_ignored_descendants(empty_snapshot):
    app = empty_snapshot
    recorded = app.region / "recorded" / "keep.txt"
    recorded.parent.mkdir()
    recorded.write_bytes(b"recorded ignore")
    app.config.snapshots.ignored_paths = ["world/region/recorded"]
    snapshot = await app.service.create_snapshot([app.data / "world"])
    app.config.snapshots.ignored_paths = ["world/region/current"]
    current = app.region / "current" / "keep.txt"
    current.parent.mkdir()
    current.write_bytes(b"current ignore")
    extra = app.region / "extra" / "delete.txt"
    extra.parent.mkdir()
    extra.write_bytes(b"remove")
    events = [event async for event in app.service.restore(snapshot.id, [app.region])]
    assert recorded.read_bytes() == b"recorded ignore"
    assert current.read_bytes() == b"current ignore"
    assert not extra.parent.exists()
    assert app.region.is_dir()
    assert {event.item for event in events if event.action == "deleted"} == {str(extra), str(extra.parent)}


async def test_missing_selected_file_is_removed_when_snapshot_parent_contains_unselected_marker(empty_snapshot):
    app = empty_snapshot
    marker = app.region / ".mc-admin-absence-test"
    marker.mkdir()
    sibling = app.region / "r.1.0.mca"
    sibling.write_bytes(b"snapshot sibling")
    snapshot = await app.service.create_snapshot([app.region])
    selected = app.region / "r.0.0.mca"
    selected.write_bytes(b"selected live file")
    sibling.write_bytes(b"unselected live sibling")
    events = [event async for event in app.service.restore(snapshot.id, [selected])]
    assert not selected.exists()
    assert marker.is_dir()
    assert sibling.read_bytes() == b"unselected live sibling"
    assert {event.item for event in events if event.action == "deleted"} == {str(selected)}


@pytest.mark.parametrize("scope", ["directory", "file"])
async def test_empty_restore_dry_run_matches_deletion_events_without_writing(empty_snapshot, scope):
    app = empty_snapshot
    selected = app.region / "r.0.0.mca"
    selected.write_bytes(b"preview-only")
    targets = [app.region] if scope == "directory" else [selected]
    preview = await app.service.preview(app.snapshot.id, targets)
    assert selected.read_bytes() == b"preview-only"
    actual = [event async for event in app.service.restore(app.snapshot.id, targets)]
    assert [event.model_dump() for event in preview] == [event.model_dump() for event in actual if event.kind == "file"]
    assert not selected.exists()


@pytest.mark.parametrize("scope", ["directory", "file"])
async def test_empty_stage_does_not_delete_existing_destination(empty_snapshot, tmp_path, scope):
    app = empty_snapshot
    selected = app.region / "r.0.0.mca"
    targets = [app.region] if scope == "directory" else [selected]
    stage = tmp_path / "stage"
    destination = app.service.stage_destination(stage, selected)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"retained-staged-file")
    events = [event async for event in app.service.stage(app.snapshot.id, targets, stage)]
    assert destination.read_bytes() == b"retained-staged-file"
    assert not any(event.action == "deleted" for event in events)


async def test_empty_restore_rejects_external_symlink_before_removing_any_sibling(empty_snapshot, tmp_path):
    app = empty_snapshot
    selected = app.region / "a.mca"
    selected.write_bytes(b"still-live")
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "secret.txt"
    external.write_bytes(b"outside")
    (app.region / "z-redirect").symlink_to(outside, target_is_directory=True)
    with pytest.raises(async_fs.PathOutsideBaseError):
        _ = [event async for event in app.service.restore(app.snapshot.id, [app.region])]
    assert selected.read_bytes() == b"still-live"
    assert external.read_bytes() == b"outside"


async def test_empty_restore_cancellation_waits_for_finite_deletion(empty_snapshot, monkeypatch):
    app = empty_snapshot
    first, second = app.region / "a.mca", app.region / "b.mca"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    entered, release = asyncio.Event(), asyncio.Event()
    original = service_module.aioos.unlink

    async def remove_then_pause(path):
        await original(path)
        if path == first:
            entered.set()
            await release.wait()

    monkeypatch.setattr(service_module.aioos, "unlink", remove_then_pause)

    async def restore():
        return [event async for event in app.service.restore(app.snapshot.id, [app.region])]

    task = asyncio.create_task(restore())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not first.exists() and second.exists()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)
    assert not first.exists() and not second.exists()
