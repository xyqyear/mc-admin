import asyncio
import json
import shlex
import shutil
from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.background_tasks.types import TaskStatus
from app.minecraft import MCServerStatus
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)
from app.runtime_resources import current_runtime
from app.snapshots.queries import RestorationQueries
from app.snapshots.restoration_models import Restoration, RestorationStatus
from app.snapshots.scopes import GlobalScope, PathsScope

pytestmark = pytest.mark.binary("restic")


async def complete(case, accepted, *, success=True):
    future = case.tasks.get_future(accepted["task_id"])
    assert future is not None
    result = await asyncio.wait_for(asyncio.shield(future), 30)
    assert result.success is success, result
    task = case.tasks.get_task(accepted["task_id"])
    assert task.status is (TaskStatus.COMPLETED if success else TaskStatus.FAILED), task
    if accepted.get("restoration_id"):
        row = await case.commands.store.get(accepted["restoration_id"])
        assert row.operation_id == accepted["task_id"]
        assert row.status is (
            RestorationStatus.SUCCEEDED if success else RestorationStatus.FAILED
        )
    return result.data


async def test_online_file_restore_and_repeated_rollback_replace_later_edits(case):
    target = case.data / "settings.txt"
    target.write_text("snapshot value")
    scope = PathsScope(server_id="survival", paths=("settings.txt",))
    created = await complete(case, await case.commands.create(scope, 1))
    target.write_text("before restore")
    case.instance.status = MCServerStatus.HEALTHY
    accepted = await case.commands.restore(scope, created["snapshot"]["id"], 1)
    await complete(case, accepted)
    assert target.read_text() == "snapshot value"
    target.write_text("edited after restore")
    rollback = await case.commands.rollback(accepted["restoration_id"], 1)
    await complete(case, rollback)
    assert target.read_text() == "before restore"
    row = await case.commands.store.get(rollback["restoration_id"])
    assert row.rollback_of_id == accepted["restoration_id"]
    target.write_text("edited after rollback")
    await complete(case, await case.commands.rollback(rollback["restoration_id"], 1))
    assert target.read_text() == "edited after restore"


async def test_missing_target_rollback_preserves_new_siblings_and_ignored_descendants(
    case,
):
    target = case.data / "plugins" / "example"
    target.mkdir(parents=True)
    (target / "setting.yml").write_text("snapshot")
    source = await case.snapshots.create_snapshot([target])
    shutil.rmtree(case.data / "plugins")
    scope = PathsScope(server_id="survival", paths=("plugins/example",))
    accepted = await case.commands.restore(scope, source.id, 1)
    await complete(case, accepted)
    assert (target / "setting.yml").read_text() == "snapshot"
    (target.parent / "other.txt").write_text("later unrelated sibling")
    (target / "ignored").mkdir()
    (target / "ignored" / "keep").write_text("protected")
    case.config.snapshots.ignored_paths = ["plugins/example/ignored"]
    rollback = await case.commands.rollback(accepted["restoration_id"], 1)
    await complete(case, rollback)
    assert not (target / "setting.yml").exists()
    assert (target / "ignored" / "keep").read_text() == "protected"
    assert (target.parent / "other.txt").read_text() == "later unrelated sibling"


async def test_source_absence_removes_only_requested_path(case):
    parent = case.data / "plugins"
    parent.mkdir()
    source = await case.snapshots.create_snapshot([parent])
    target = parent / "example" / "settings"
    target.mkdir(parents=True)
    (target / "value").write_text("new content")
    (parent / "keep").write_text("unrelated")
    scope = PathsScope(server_id="survival", paths=("plugins/example/settings",))
    await complete(case, await case.commands.restore(scope, source.id, 1))
    assert not target.exists()
    assert (parent / "keep").read_text() == "unrelated"


async def test_safety_persistence_failure_never_writes_target(case, monkeypatch):
    target = case.data / "setting"
    target.write_text("snapshot")
    source = await case.snapshots.create_snapshot([target])
    target.write_text("must survive")

    async def failed(*args):
        raise OSError("injected history storage failure")

    monkeypatch.setattr(case.commands.store, "save_safety", failed)
    accepted = await case.commands.restore(
        PathsScope(server_id="survival", paths=("setting",)), source.id, 1
    )
    await complete(case, accepted, success=False)
    assert target.read_text() == "must survive"
    record = await case.journal.get(accepted["task_id"])
    assert not record.data_changed
    assert any(ref.kind == "safety_snapshot" for ref in record.recovery_refs)


async def test_queued_global_snapshot_protects_repository_and_server_until_cancelled(
    case, monkeypatch
):
    (case.data / "keep").write_text("retained")

    async def pause_start(_):
        await asyncio.Event().wait()

    monkeypatch.setattr(case.journal, "start", pause_start)

    accepted = await case.commands.create(GlobalScope(), 1)
    with pytest.raises(HTTPException) as blocked:
        case.commands.require_deletable("survival")
    assert blocked.value.status_code == 423
    with pytest.raises(HTTPException):
        await case.snapshots.unlock()
    assert await case.tasks.cancel(accepted["task_id"])
    result = await case.tasks.get_future(accepted["task_id"])
    assert not result.success
    assert (case.data / "keep").read_text() == "retained"
    case.commands.require_deletable("survival")
    await case.snapshots.unlock()


async def test_duplicate_restore_and_queued_cancel_have_one_terminal_history(
    case, monkeypatch
):
    target = case.data / "setting"
    target.write_text("snapshot")
    source = await case.snapshots.create_snapshot([target])
    target.write_text("present")
    scope = PathsScope(server_id="survival", paths=("setting",))

    async def pause_start(_):
        await asyncio.Event().wait()

    monkeypatch.setattr(case.journal, "start", pause_start)

    accepted = await case.commands.restore(scope, source.id, 1)
    with pytest.raises(HTTPException) as duplicate:
        await case.commands.restore(scope, source.id, 1)
    assert duplicate.value.status_code == 423
    assert cast(dict, duplicate.value.detail)["task_id"] == accepted["task_id"]
    assert await case.tasks.cancel(accepted["task_id"])
    await case.tasks.get_future(accepted["task_id"])
    async with current_runtime().database.session_factory() as session:
        rows = list(await session.scalars(select(Restoration)))
    assert len(rows) == 1
    assert rows[0].status is RestorationStatus.CANCELLED
    assert rows[0].safety_snapshot_id is None
    record = await case.journal.get(accepted["task_id"])
    assert record.state is OperationState.CANCELLED and record.writers_stopped
    assert target.read_text() == "present"
    await case.snapshots.forget_id(source.id)


async def test_original_protection_survives_current_rule_removal_and_rollback(case):
    folder = case.data / "plugins"
    folder.mkdir()
    (folder / "value").write_text("source")
    (folder / "ignored").write_text("protected source")
    case.config.snapshots.ignored_paths = ["plugins/ignored"]
    source = await case.snapshots.create_snapshot([folder])
    case.config.snapshots.ignored_paths = []
    (folder / "value").write_text("before restore")
    (folder / "ignored").write_text("protected live")
    scope = PathsScope(server_id="survival", paths=("plugins",))
    accepted = await case.commands.restore(scope, source.id, 1)
    await complete(case, accepted)
    assert (folder / "value").read_text() == "source"
    assert (folder / "ignored").read_text() == "protected live"
    row = await case.commands.store.get(accepted["restoration_id"])
    assert str(folder / "ignored") in json.loads(row.protection_json)["excluded"]
    (folder / "ignored").write_text("protected newer")
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert (folder / "value").read_text() == "before restore"
    assert (folder / "ignored").read_text() == "protected newer"


async def test_cancel_after_history_acceptance_has_no_worker_or_live_write(
    case, monkeypatch
):
    target = case.data / "setting"
    target.write_text("snapshot")
    source = await case.snapshots.create_snapshot([target])
    target.write_text("present")
    committed = asyncio.Event()
    accept = case.commands.store.accept

    async def pause(**kwargs):
        await accept(**kwargs)
        committed.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(case.commands.store, "accept", pause)
    request = asyncio.create_task(
        case.commands.restore(
            PathsScope(server_id="survival", paths=("setting",)), source.id, 1
        )
    )
    await asyncio.wait_for(committed.wait(), 5)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    async with current_runtime().database.session_factory() as session:
        rows = list(await session.scalars(select(Restoration)))
    assert len(rows) == 1 and rows[0].status is RestorationStatus.CANCELLED
    assert case.tasks.get_all_tasks() == []
    assert (
        await case.journal.get(rows[0].operation_id)
    ).state is OperationState.CANCELLED
    assert target.read_text() == "present"
    case.commands.require_deletable("survival")
    await case.snapshots.forget_id(source.id)


async def test_failed_history_acceptance_has_no_worker_and_no_live_write(
    case, monkeypatch
):
    target = case.data / "setting"
    target.write_text("snapshot")
    source = await case.snapshots.create_snapshot([target])
    target.write_text("present")

    async def failed(**kwargs):
        raise OSError("synthetic history failure")

    monkeypatch.setattr(case.commands.store, "accept", failed)
    with pytest.raises(OSError):
        await case.commands.restore(
            PathsScope(server_id="survival", paths=("setting",)), source.id, 1
        )
    async with current_runtime().database.session_factory() as session:
        assert list(await session.scalars(select(Restoration))) == []
    assert case.tasks.get_all_tasks() == []
    assert (await case.journal.list())[0].state is OperationState.FAILED
    assert target.read_text() == "present"
    case.commands.require_deletable("survival")


async def test_ignored_symlink_is_preserved_when_restoring_its_parent(case):
    folder = case.data / "plugins"
    folder.mkdir()
    (folder / "value").write_text("original")
    (folder / "cache").mkdir()
    case.config.snapshots.ignored_paths = ["plugins/cache"]
    source = await case.snapshots.create_snapshot([folder])
    (folder / "cache").rmdir()
    (case.data / "cache-target").mkdir()
    (case.data / "cache-target" / "keep").write_text("protected live data")
    (folder / "cache").symlink_to(case.data / "cache-target", target_is_directory=True)
    (folder / "value").write_text("modified")
    await complete(
        case,
        await case.commands.restore(
            PathsScope(server_id="survival", paths=("plugins",)), source.id, 1
        ),
    )
    assert (folder / "value").read_text() == "original"
    assert (folder / "cache").is_symlink()
    assert (folder / "cache" / "keep").read_text() == "protected live data"


async def test_cancel_real_restic_between_targets_retains_safe_rollback(
    case, tmp_path, monkeypatch
):
    for name in ("a", "b"):
        (case.data / name).mkdir()
        (case.data / name / "value").write_text("source " + name)
    targets = [case.data / name for name in ("a", "b")]
    source = await case.snapshots.create_snapshot(targets)
    for name in ("a", "b"):
        (case.data / name / "value").write_text("before " + name)
    real = case.client.binary_path
    marker = tmp_path / "first-restore-completed"
    wrapper = tmp_path / "restic-controlled"
    wrapper.write_text(
        "#!/bin/sh\n" + shlex.quote(str(real)) + ' "$@"\nresult=$?\n'
        'if [ "$1" = "restore" ] && [ "$result" = "0" ]; then\n'
        + "touch "
        + shlex.quote(str(marker))
        + "\nsleep 300\nfi\nexit $result\n"
    )
    wrapper.chmod(0o755)
    monkeypatch.setattr(case.client, "binary_path", wrapper)
    accepted = await case.commands.restore(
        PathsScope(server_id="survival", paths=("a", "b")), source.id, 1
    )

    async def wait_for_write():
        from app.utils.async_fs import lexists

        while not await lexists(marker):
            await asyncio.sleep(0.02)

    try:
        await asyncio.wait_for(wait_for_write(), 30)
        assert (case.data / "a" / "value").read_text() == "source a"
        assert (case.data / "b" / "value").read_text() == "before b"
    finally:
        await case.tasks.cancel(accepted["task_id"])
        await asyncio.wait_for(case.tasks.get_future(accepted["task_id"]), 15)
    row = await case.commands.store.get(accepted["restoration_id"])
    assert row.status is RestorationStatus.CANCELLED and row.safety_snapshot_id
    record = await case.journal.get(accepted["task_id"])
    assert record.state is OperationState.CANCELLED and record.writers_stopped
    assert not record.processes and record.data_changed
    monkeypatch.setattr(case.client, "binary_path", real)
    await complete(case, await case.commands.rollback(row.id, 1))
    assert (case.data / "a" / "value").read_text() == "before a"
    assert (case.data / "b" / "value").read_text() == "before b"


async def test_history_survives_retention_without_permanently_pinning_safety(case):
    target = case.data / "value"
    target.write_text("source")
    source = await case.snapshots.create_snapshot([target])
    target.write_text("before")
    accepted = await case.commands.restore(
        PathsScope(server_id="survival", paths=("value",)), source.id, 1
    )
    result = await complete(case, accepted)
    queries = RestorationQueries(
        current_runtime().database.session_factory, case.snapshots
    )
    row = await queries.get(accepted["restoration_id"])
    assert row.rollback_available and row.safety_snapshot_exists
    await case.snapshots.forget_id(source.id)
    row = await queries.get(accepted["restoration_id"])
    assert not row.source_snapshot_exists and row.rollback_available
    await case.snapshots.forget_id(result["safety_snapshot_id"])
    row = await queries.get(accepted["restoration_id"])
    assert not row.rollback_available and not row.safety_snapshot_exists
    assert row.rollback_unavailable_reason == "安全快照不存在，可能已按保留策略删除"
    assert row.status is RestorationStatus.SUCCEEDED
    assert target.read_text() == "source"


async def test_slow_repository_lookup_is_observable_after_acceptance(case, monkeypatch):
    target = case.data / "value"
    target.write_text("source")
    source = await case.snapshots.create_snapshot([target])
    target.write_text("untouched while preparing")
    entered = asyncio.Event()

    async def delayed_source(_):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(case.snapshots, "get_snapshot", delayed_source)
    accepted = await asyncio.wait_for(
        case.commands.restore(
            PathsScope(server_id="survival", paths=("value",)), source.id, 1
        ),
        5,
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task = case.tasks.get_task(accepted["task_id"])
        assert task.status is TaskStatus.RUNNING
        assert task.message == "正在检查源快照和保护范围"
        assert target.read_text() == "untouched while preparing"
        assert (
            await case.commands.store.get(accepted["restoration_id"])
        ).safety_snapshot_id is None
        with pytest.raises(HTTPException):
            await case.snapshots.forget_id(source.id)
    finally:
        await case.tasks.cancel(accepted["task_id"])
        await case.tasks.get_future(accepted["task_id"])
    assert (
        await case.commands.store.get(accepted["restoration_id"])
    ).status is RestorationStatus.CANCELLED
    assert target.read_text() == "untouched while preparing"


async def test_global_restore_preserves_project_and_unregistered_content_scope(case):
    root = case.data.parent.parent
    (root / "shared.txt").write_text("shared original")
    (case.data / "value").write_text("server original")
    created = await complete(case, await case.commands.create(GlobalScope(), 1))
    (root / "shared.txt").write_text("shared later")
    (case.data / "value").write_text("server later")
    accepted = await case.commands.restore(GlobalScope(), created["snapshot"]["id"], 1)
    await complete(case, accepted)
    assert (root / "shared.txt").read_text() == "shared original"
    assert (case.data / "value").read_text() == "server original"
    queries = RestorationQueries(
        current_runtime().database.session_factory, case.snapshots
    )
    history = await queries.history("survival", 50, 0)
    assert history.total == 1
    assert history.restorations[0].id == accepted["restoration_id"]
    assert history.restorations[0].server_id is None
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert (root / "shared.txt").read_text() == "shared later"
    assert (case.data / "value").read_text() == "server later"


async def test_source_exclusion_rejection_remains_readable_after_rules_are_removed(
    case,
):
    target = case.data / "ignored"
    target.write_text("protected")
    case.config.snapshots.ignored_paths = ["ignored"]
    source = await case.snapshots.create_snapshot([case.data])
    case.config.snapshots.ignored_paths = []
    accepted = await case.commands.restore(
        PathsScope(server_id="survival", paths=("ignored",)), source.id, 1
    )
    await complete(case, accepted, success=False)
    assert "忽略" in case.tasks.get_task(accepted["task_id"]).error
    assert target.read_text() == "protected"
    assert len(await case.snapshots.list_snapshots()) == 1
    assert (
        await case.commands.store.get(accepted["restoration_id"])
    ).safety_snapshot_id is None


async def test_unconfirmed_cron_repository_writer_blocks_deletion_after_memory_references_release(
    case,
):
    target = case.data / "value"
    target.write_text("retained")
    source = await case.snapshots.create_snapshot([target])
    operation = await case.journal.accept(
        OperationSpec("cron_backup", (ResourceReference("files"),))
    )
    await case.journal.start(operation.operation_id)
    await case.journal.set_ownership_known(operation.operation_id, False)
    await case.journal.finish(
        operation.operation_id, OperationState.INTERRUPTED, writers_stopped=False
    )
    try:
        assert not case.snapshots.repository_use.active_snapshots
        with pytest.raises(HTTPException) as blocked:
            await case.snapshots.forget_id(source.id)
        assert blocked.value.status_code == 423
        assert [row.id for row in await case.snapshots.list_snapshots()] == [source.id]
    finally:
        await case.journal.resolve(
            operation.operation_id, actor_id=1, writers_stopped=True
        )
    await case.snapshots.forget_id(source.id)
    assert await case.snapshots.list_snapshots() == []
