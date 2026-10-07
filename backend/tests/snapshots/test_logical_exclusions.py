import asyncio
import json

import pytest

from app.snapshots.evidence import snapshot_selection
from app.snapshots.planner import TargetIgnoredError
from app.snapshots.scopes import PathsScope

from .support import complete

pytestmark = pytest.mark.binary("restic")


def alias(case):
    target = case.data / "target"
    target.mkdir()
    (target / "value").write_text("snapshot")
    (case.data / "alias").symlink_to(target, target_is_directory=True)
    return target, PathsScope(server_id="survival", paths=("alias",))


async def test_ignored_target_does_not_block_alias_backup_restore_or_rollback(case):
    target, scope = alias(case)
    case.config.snapshots.ignored_paths = ["target"]
    with pytest.raises(TargetIgnoredError):
        await case.commands.create(
            PathsScope(server_id="survival", paths=("target",)), 1
        )
    created = await complete(case, await case.commands.create(scope, 1))
    source = await case.snapshots.get_snapshot(created["snapshot"]["id"])
    evidence = snapshot_selection(source)
    assert evidence is not None
    assert [(item.logical, item.execution) for item in evidence.mappings] == [
        (case.data / "alias", target)
    ]
    assert source.excludes == []
    assert source.id in {item.id for item in await case.commands.eligible(scope)}
    (target / "value").write_text("before restore")
    accepted = await case.commands.restore(scope, source.id, 1)
    await complete(case, accepted)
    assert (target / "value").read_text() == "snapshot"
    row = await case.commands.store.get(accepted["restoration_id"])
    assert json.loads(row.scope_json)["version"] == 2
    assert json.loads(row.protection_json)["semantics"] == "logical"
    await complete(case, await case.commands.rollback(row.id, 1))
    assert (target / "value").read_text() == "before restore"
    assert (case.data / "alias").is_symlink()


async def test_ignored_alias_does_not_block_its_target(case):
    target, scope = alias(case)
    case.config.snapshots.ignored_paths = ["alias"]
    with pytest.raises(TargetIgnoredError):
        await case.commands.create(scope, 1)
    target_scope = PathsScope(server_id="survival", paths=("target",))
    created = await complete(case, await case.commands.create(target_scope, 1))
    (target / "value").write_text("modified")
    await complete(
        case, await case.commands.restore(target_scope, created["snapshot"]["id"], 1)
    )
    assert (target / "value").read_text() == "snapshot"


async def test_alias_descendant_exclusion_maps_to_execution_and_survives_rule_removal(
    case,
):
    target, scope = alias(case)
    (target / "keep").write_text("excluded original")
    case.config.snapshots.ignored_paths = ["alias/keep"]
    created = await complete(case, await case.commands.create(scope, 1))
    source = await case.snapshots.get_snapshot(created["snapshot"]["id"])
    assert source.excludes == [str(target / "keep")]
    (target / "keep").write_text("protected live")
    (target / "value").write_text("changed")
    case.config.snapshots.ignored_paths = []
    accepted = await case.commands.restore(scope, source.id, 1)
    await complete(case, accepted)
    assert (target / "value").read_text() == "snapshot"
    assert (target / "keep").read_text() == "protected live"
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert (target / "value").read_text() == "changed"
    assert (target / "keep").read_text() == "protected live"


async def test_joint_alias_backup_keeps_data_allowed_through_another_name(case):
    target, _ = alias(case)
    (target / "keep").write_text("allowed through alias")
    case.config.snapshots.ignored_paths = ["target/keep"]
    scope = PathsScope(server_id="survival", paths=("target", "alias"))
    created = await complete(case, await case.commands.create(scope, 1))
    source = await case.snapshots.get_snapshot(created["snapshot"]["id"])
    assert source.excludes == []
    nodes = await case.client.ls(source.id, target)
    assert target / "keep" in nodes
    (target / "keep").write_text("changed")
    await complete(
        case,
        await case.commands.restore(
            PathsScope(server_id="survival", paths=("alias",)), source.id, 1
        ),
    )
    assert (target / "keep").read_text() == "allowed through alias"


async def test_accepted_alias_retarget_is_rejected_before_backup(case, monkeypatch):
    target, scope = alias(case)
    other = case.data / "other"
    other.mkdir()
    (other / "value").write_text("other live")
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = case.commands._planner.revalidate

    async def gated(prepared):
        entered.set()
        await proceed.wait()
        await original(prepared)

    monkeypatch.setattr(case.commands._planner, "revalidate", gated)
    accepted = await case.commands.create(scope, 1)
    await asyncio.wait_for(entered.wait(), 10)
    (case.data / "alias").unlink()
    (case.data / "alias").symlink_to(other, target_is_directory=True)
    proceed.set()
    await complete(case, accepted, success=False)
    assert (target / "value").read_text() == "snapshot"
    assert (other / "value").read_text() == "other live"
    assert await case.client.list_snapshots() == []


async def test_inexpressible_nested_alias_exclusions_fail_without_a_snapshot(case):
    target, _ = alias(case)
    (target / "blocked" / "selected").mkdir(parents=True)
    (target / "blocked" / "selected" / "value").write_text("selected content")
    (case.data / "nested-alias").symlink_to(
        target / "blocked" / "selected", target_is_directory=True
    )
    case.config.snapshots.ignored_paths = ["target/blocked"]
    scope = PathsScope(server_id="survival", paths=("target", "nested-alias"))
    accepted = await case.commands.create(scope, 1)
    await complete(case, accepted, success=False)
    assert await case.client.list_snapshots() == []
    assert (target / "blocked" / "selected" / "value").read_text() == "selected content"


async def test_retargeted_source_is_skipped_without_hiding_current_candidates(case):
    target, scope = alias(case)
    old = await complete(case, await case.commands.create(scope, 1))
    other = case.data / "other"
    other.mkdir()
    (other / "value").write_text("current source")
    (case.data / "alias").unlink()
    (case.data / "alias").symlink_to(other, target_is_directory=True)
    current = await complete(case, await case.commands.create(scope, 1))
    candidates = await case.commands.eligible(scope)
    assert {item.id for item in candidates} == {current["snapshot"]["id"]}
    accepted = await case.commands.restore(scope, old["snapshot"]["id"], 1)
    await complete(case, accepted, success=False)
    assert (
        await case.commands.store.get(accepted["restoration_id"])
    ).safety_snapshot_id is None
    assert (target / "value").read_text() == "snapshot"
    assert (other / "value").read_text() == "current source"


async def test_new_snapshot_identity_roots_cannot_be_reinterpreted_after_link_change(
    case,
):
    first, second = case.data / "a", case.data / "b"
    first.write_text("first source")
    second.write_text("second source")
    scope = PathsScope(server_id="survival", paths=("a", "b"))
    created = await complete(case, await case.commands.create(scope, 1))
    first.unlink()
    first.symlink_to(second)
    second.write_text("must survive")
    selected = PathsScope(server_id="survival", paths=("a",))
    assert await case.commands.eligible(selected) == []
    accepted = await case.commands.restore(selected, created["snapshot"]["id"], 1)
    await complete(case, accepted, success=False)
    assert (
        await case.commands.store.get(accepted["restoration_id"])
    ).safety_snapshot_id is None
    assert second.read_text() == "must survive"
    assert first.is_symlink()


async def test_alias_missing_target_rollback_removes_real_parents_and_preserves_link(
    case,
):
    target = case.data / "real" / "nested"
    target.mkdir(parents=True)
    (target / "value").write_text("source contents")
    link = case.data / "alias"
    link.symlink_to(target, target_is_directory=True)
    scope = PathsScope(server_id="survival", paths=("alias/value",))
    created = await complete(case, await case.commands.create(scope, 1))
    (target / "value").unlink()
    target.rmdir()
    target.parent.rmdir()
    accepted = await case.commands.restore(scope, created["snapshot"]["id"], 1)
    await complete(case, accepted)
    assert (target / "value").read_text() == "source contents"
    row = await case.commands.store.get(accepted["restoration_id"])
    evidence = json.loads(row.selection_json)
    assert set(evidence["absent_parents"]) == {str(target), str(target.parent)}
    await complete(case, await case.commands.rollback(row.id, 1))
    assert not target.parent.exists()
    assert link.is_symlink()
    assert link.readlink() == target


async def test_compressed_alias_source_keeps_its_selected_subtree_identity(case):
    target = case.data / "real"
    (target / "left").mkdir(parents=True)
    (target / "left" / "value").write_text("selected source")
    (target / "right" / "left").mkdir(parents=True)
    (target / "right" / "left" / "value").write_text("different subtree source")
    link = case.data / "alias"
    link.symlink_to(target, target_is_directory=True)
    created = await complete(
        case,
        await case.commands.create(
            PathsScope(server_id="survival", paths=("alias/left", "alias/right")), 1
        ),
    )
    link.unlink()
    link.symlink_to(target / "right", target_is_directory=True)
    current = target / "right" / "left" / "value"
    current.write_text("must survive")
    selected = PathsScope(server_id="survival", paths=("alias/left/value",))
    assert await case.commands.eligible(selected) == []
    accepted = await case.commands.restore(selected, created["snapshot"]["id"], 1)
    await complete(case, accepted, success=False)
    assert current.read_text() == "must survive"


async def test_new_identity_directory_source_rejects_changed_root_for_child_selection(
    case,
):
    first, second = case.data / "a", case.data / "b"
    first.mkdir()
    second.mkdir()
    (first / "value").write_text("first source")
    (second / "value").write_text("second source")
    created = await complete(
        case,
        await case.commands.create(
            PathsScope(server_id="survival", paths=("a", "b")), 1
        ),
    )
    (first / "value").unlink()
    first.rmdir()
    first.symlink_to(second, target_is_directory=True)
    current = second / "value"
    current.write_text("must survive")
    selected = PathsScope(server_id="survival", paths=("a/value",))
    assert await case.commands.eligible(selected) == []
    accepted = await case.commands.restore(selected, created["snapshot"]["id"], 1)
    await complete(case, accepted, success=False)
    assert current.read_text() == "must survive"
    assert first.is_symlink()


async def test_parent_source_allows_existing_internal_link_child_selection(case):
    target, _ = alias(case)
    created = await complete(
        case,
        await case.commands.create(PathsScope(server_id="survival", paths=(".",)), 1),
    )
    (target / "value").write_text("live value")
    selected = PathsScope(server_id="survival", paths=("alias/value",))
    assert created["snapshot"]["id"] in {
        source.id for source in await case.commands.eligible(selected)
    }
    await complete(
        case, await case.commands.restore(selected, created["snapshot"]["id"], 1)
    )
    assert (target / "value").read_text() == "snapshot"
    assert (case.data / "alias").is_symlink()
