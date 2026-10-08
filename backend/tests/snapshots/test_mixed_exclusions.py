import asyncio
import json

import pytest

from app.minecraft import MCServerStatus
from app.runtime_resources import current_runtime
from app.snapshots.planner import TargetIgnoredError
from app.snapshots.scopes import PathsScope

from .support import complete

pytestmark = pytest.mark.binary("restic")


async def test_mixed_creation_skips_ignored_roots_including_missing_ones(case):
    allowed = case.data / "config.txt"
    allowed.write_text("source")
    protected = case.data / "private.txt"
    protected.write_text("never back up")
    case.config.snapshots.ignored_paths = ["private.txt", "missing"]
    scope = PathsScope(server_id="survival", paths=("config.txt", "private.txt", "missing"))
    result = await complete(case, await case.commands.create(scope, 1))
    source = await case.snapshots.get_snapshot(result["snapshot"]["id"])
    assert source.paths == [str(allowed)]
    assert set(result["skipped_paths"]) == {str(protected), str(case.data / "missing")}
    tree = await case.client.ls(source.id, case.data)
    assert allowed in tree and protected not in tree
    assert protected.read_text() == "never back up"


@pytest.mark.parametrize("historical", [False, True])
async def test_mixed_restore_preview_and_rollback_preserve_ignored_world_online(case, historical):
    allowed = case.data / "config.txt"
    allowed.write_text("source")
    world = case.data / "world"
    world.mkdir()
    protected = world / "value.dat"
    protected.write_text("protected source")
    case.config.snapshots.ignored_paths = ["world"]
    source = await case.snapshots.create_snapshot([case.data])
    if historical:
        case.config.snapshots.ignored_paths = []
    scope = PathsScope(server_id="survival", paths=("world", "config.txt"))
    allowed.write_text("before restore")
    protected.write_text("live world")
    case.instance.status = MCServerStatus.RUNNING
    candidates = await case.commands.eligible(scope)
    assert [item.id for item in candidates] == [source.id]
    assert candidates[0].skipped_paths == [str(world)]
    previews = current_runtime().snapshot_previews
    assert previews is not None
    result = await complete(case, await previews.submit(scope, source.id, 1))
    assert result["skipped_paths"] == [str(world)]
    actions = await previews.actions(result["preview_id"], 0, 100)
    assert [action.item for action in actions.actions] == [str(allowed)]
    assert allowed.read_text() == "before restore"
    accepted = await case.commands.restore(scope, source.id, 1, preview_id=result["preview_id"])
    await complete(case, accepted)
    assert accepted["skipped_paths"] == [str(world)]
    assert allowed.read_text() == "source"
    assert protected.read_text() == "live world"
    row = await case.commands.store.get(accepted["restoration_id"])
    assert set(json.loads(row.scope_json)["paths"]) == {str(world), str(allowed)}
    assert str(world) in json.loads(row.protection_json)["excluded"]
    safety = await case.snapshots.get_snapshot(row.safety_snapshot_id)
    assert safety.paths == [str(allowed)]
    case.config.snapshots.ignored_paths = []
    protected.write_text("world after restore")
    await complete(case, await case.commands.rollback(row.id, 1))
    assert allowed.read_text() == "before restore"
    assert protected.read_text() == "world after restore"


async def test_uncovered_allowed_root_is_not_silently_skipped(case):
    allowed = case.data / "config.txt"
    allowed.write_text("source")
    source = await case.snapshots.create_snapshot([allowed])
    allowed.write_text("live config")
    other = case.data / "other.txt"
    other.write_text("live other")
    case.config.snapshots.ignored_paths = ["private"]
    scope = PathsScope(server_id="survival", paths=("config.txt", "other.txt", "private"))
    assert await case.commands.eligible(scope) == []
    accepted = await case.commands.restore(scope, source.id, 1)
    await complete(case, accepted, success=False)
    assert allowed.read_text() == "live config" and other.read_text() == "live other"
    row = await case.commands.store.get(accepted["restoration_id"])
    assert row.safety_snapshot_id is None
    assert len(await case.snapshots.list_snapshots()) == 1


async def test_all_protected_selections_reject_before_task_acceptance(case):
    folder = case.data / "private"
    folder.mkdir()
    (folder / "value").write_text("protected")
    case.config.snapshots.ignored_paths = ["private"]
    source = await case.snapshots.create_snapshot([case.data])
    scope = PathsScope(server_id="survival", paths=("private",))
    previews = current_runtime().snapshot_previews
    assert previews is not None
    for action in (
        lambda: case.commands.create(scope, 1),
        lambda: case.commands.restore(scope, source.id, 1),
        lambda: previews.submit(scope, source.id, 1),
    ):
        with pytest.raises(TargetIgnoredError, match="没有可处理的内容"):
            await action()
    case.config.snapshots.ignored_paths = []
    assert await case.commands.eligible(scope) == []
    with pytest.raises(TargetIgnoredError):
        await case.commands.restore(scope, source.id, 1)
    with pytest.raises(TargetIgnoredError):
        await previews.submit(scope, source.id, 1)
    assert (folder / "value").read_text() == "protected"
    assert not case.tasks.get_all_tasks()


async def test_queued_restore_rejects_changed_rules_before_safety_and_write(case, monkeypatch):
    allowed = case.data / "config.txt"
    allowed.write_text("source")
    source = await case.snapshots.create_snapshot([allowed])
    allowed.write_text("must survive")
    case.config.snapshots.ignored_paths = ["private"]
    release = asyncio.Event()
    start = case.journal.start

    async def held_start(operation_id):
        await release.wait()
        await start(operation_id)

    monkeypatch.setattr(case.journal, "start", held_start)
    scope = PathsScope(server_id="survival", paths=("config.txt", "private"))
    accepted = await case.commands.restore(scope, source.id, 1)
    case.config.snapshots.ignored_paths = []
    release.set()
    await complete(case, accepted, success=False)
    assert allowed.read_text() == "must survive"
    row = await case.commands.store.get(accepted["restoration_id"])
    assert row.safety_snapshot_id is None
    assert len(await case.snapshots.list_snapshots()) == 1
