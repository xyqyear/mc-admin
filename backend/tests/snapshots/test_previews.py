import asyncio
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.background_tasks.types import TaskStatus
from app.operations.journal_types import OperationState
from app.runtime_resources import current_runtime
from app.snapshots.restoration_models import Restoration
from app.snapshots.scopes import PathsScope

from .support import complete

pytestmark = pytest.mark.binary("restic")


async def prepared(case, count=1):
    target = case.data / "config"
    target.mkdir()
    for n in range(count):
        (target / f"{n:03}.txt").write_text(f"snapshot {n}")
    scope = PathsScope(server_id="survival", paths=("config",))
    source = (await complete(case, await case.commands.create(scope, 1)))["snapshot"]["id"]
    for n in range(count):
        (target / f"{n:03}.txt").write_text(f"live value {n}")
    return target, scope, source


async def test_file_preview_pages_actual_changes_without_safety_or_history(case):
    target, scope, source = await prepared(case, 205)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    before = len(await case.snapshots.list_snapshots())
    result = await complete(case, await previews.submit(scope, source, 1))
    assert result["updated"] == 205
    preview_id = result["preview_id"]
    actions, cursor = [], 0
    for expected in (100, 100, 5):
        assert cursor is not None
        page = await previews.actions(preview_id, cursor, 100)
        assert len(page.actions) == expected
        actions.extend(page.actions)
        cursor = page.next_cursor
    assert cursor is None
    assert {action.item for action in actions} == {str(path) for path in target.iterdir()}
    assert all(action.action == "updated" for action in actions)
    assert (target / "000.txt").read_text() == "live value 0"
    assert len(await case.snapshots.list_snapshots()) == before
    async with current_runtime().database.session_factory() as session:
        assert await session.scalar(select(func.count(Restoration.id))) == 0
    with pytest.raises(HTTPException):
        await case.snapshots.forget_id(source)
    directory = previews.manager.get_session_dir(preview_id)
    assert directory is not None
    await complete(case, await previews.end(preview_id, 1))
    assert not directory.exists()
    await case.snapshots.forget_id(source)


async def test_matching_preview_restores_and_rolls_back_live_state(case):
    target, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    result = await complete(case, await previews.submit(scope, source, 1))
    accepted = await case.commands.restore(scope, source, 1, preview_id=result["preview_id"])
    await complete(case, accepted)
    assert (target / "000.txt").read_text() == "snapshot 0"
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert (target / "000.txt").read_text() == "live value 0"


@pytest.mark.parametrize("change", ["source", "scope", "rules", "expiry", "generation", "target"])
async def test_stale_preview_rejects_before_safety_and_live_write(case, change):
    target, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    result = await complete(case, await previews.submit(scope, source, 1))
    preview_id = result["preview_id"]
    if change == "source":
        source = "f" * 64
    elif change == "scope":
        scope = PathsScope(server_id="survival", paths=("server.properties",))
    elif change == "rules":
        case.config.snapshots.ignored_paths = ["config/ignored"]
    elif change == "expiry":
        preview = previews.manager.get_session(preview_id)
        assert preview is not None
        preview.last_seen -= timedelta(days=1)
    elif change == "generation":
        from app.servers.models import Server
        async with current_runtime().database.session_factory() as session:
            row = await session.get(Server, 1)
            assert row is not None
            row.server_id = "retired"
            session.add(Server(server_id="survival"))
            await session.commit()
    else:
        (target / "other.txt").write_text("changed after preview")
    count = len(await case.snapshots.list_snapshots())
    with pytest.raises(HTTPException) as error:
        await case.commands.restore(scope, source, 1, preview_id=preview_id)
    assert error.value.status_code in {404, 409}
    assert len(await case.snapshots.list_snapshots()) == count
    assert (target / "000.txt").read_text() == "live value 0"


async def test_failed_preview_reports_terminal_failure_and_cleans_private_output(case, monkeypatch):
    _, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    async def fail(*args, **kwargs):
        raise RuntimeError("private adapter secret")
        yield
    monkeypatch.setattr(case.snapshots, "restore", fail)
    accepted = await previews.submit(scope, source, 1)
    await complete(case, accepted, success=False)
    task = case.tasks.get_task(accepted["task_id"])
    assert "private adapter secret" not in task.error
    record = await case.journal.get(accepted["task_id"])
    assert record.state is OperationState.FAILED and record.writers_stopped
    assert not list(previews.manager.base_dir.iterdir())
    assert not case.snapshots.repository_use.active_snapshots


async def test_preparing_preview_outlives_observer_and_explicit_cancel_cleans(case, monkeypatch):
    _, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    started, release = asyncio.Event(), asyncio.Event()
    original = case.snapshots.restore
    async def pause(*args, **kwargs):
        started.set()
        await release.wait()
        async for event in original(*args, **kwargs):
            yield event
    monkeypatch.setattr(case.snapshots, "restore", pause)
    accepted = await asyncio.wait_for(previews.submit(scope, source, 1), 2)
    await asyncio.wait_for(started.wait(), 3)
    assert case.tasks.get_task(accepted["task_id"]).status is TaskStatus.RUNNING
    with pytest.raises(HTTPException):
        await case.snapshots.forget_id(source)
    await case.tasks.cancel(accepted["task_id"])
    future = case.tasks.get_future(accepted["task_id"])
    await asyncio.wait_for(asyncio.shield(future), 5)
    assert case.tasks.get_task(accepted["task_id"]).status is TaskStatus.CANCELLED
    assert not list(previews.manager.base_dir.iterdir())
    assert not case.snapshots.repository_use.active_snapshots


async def test_cancel_during_ready_preview_finalization_releases_result_before_terminal(
    case, monkeypatch
):
    from app.snapshots import previews as preview_module

    target, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    finalizing, release = asyncio.Event(), asyncio.Event()
    original = preview_module.release_artifact

    async def pause(kind, artifact_id):
        finalizing.set()
        await release.wait()
        await original(kind, artifact_id)

    monkeypatch.setattr(preview_module, "release_artifact", pause)
    accepted = await previews.submit(scope, source, 1)
    future = case.tasks.get_future(accepted["task_id"])
    assert future is not None
    cancelling = None
    try:
        await asyncio.wait_for(finalizing.wait(), 15)
        task = case.tasks.get_task(accepted["task_id"])
        assert task is not None and task.result is not None
        preview_id = task.result["preview_id"]
        directory = previews.manager.get_session_dir(preview_id)
        assert directory is not None
        assert directory is not None and directory.exists()
        cancelling = asyncio.create_task(case.tasks.cancel(accepted["task_id"]))
        await asyncio.sleep(0)
        assert not future.done()
        with pytest.raises(HTTPException):
            await case.snapshots.forget_id(source)
        release.set()
        await cancelling
        await asyncio.wait_for(asyncio.shield(future), 10)
        assert task.status is TaskStatus.CANCELLED
        with pytest.raises(HTTPException) as expired:
            await previews.get(preview_id)
        assert expired.value.status_code == 404
        assert not directory.exists()
        assert not case.snapshots.repository_use.active_snapshots
        assert (target / "000.txt").read_text() == "live value 0"
    finally:
        release.set()
        if cancelling is not None:
            await cancelling


@pytest.mark.parametrize("inside", [True, False])
async def test_application_observed_writes_invalidate_only_the_selected_path(case, inside):
    from app.files.application import FileApplication
    target, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    preview_id = (await complete(case, await previews.submit(scope, source, 1)))["preview_id"]
    before = target.stat().st_mtime_ns
    await FileApplication(case.instance, "survival", 1).update("config/000.txt" if inside else "server.properties", "an application edit")
    assert target.stat().st_mtime_ns == before
    if inside:
        with pytest.raises(HTTPException) as error:
            await case.commands.restore(scope, source, 1, preview_id=preview_id)
        assert error.value.status_code == 409
        assert (target / "000.txt").read_text() == "an application edit"
    else:
        await complete(case, await case.commands.restore(scope, source, 1, preview_id=preview_id))
        assert (target / "000.txt").read_text() == "snapshot 0"
        assert (case.data / "server.properties").read_text() == "an application edit"


async def test_target_changed_during_preparation_does_not_publish_a_ready_preview(case, monkeypatch):
    from app.files.application import FileApplication
    target, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    entered, resume = asyncio.Event(), asyncio.Event()
    original = case.snapshots.restore
    async def slow(*args, **kwargs):
        entered.set()
        await resume.wait()
        async for event in original(*args, **kwargs):
            yield event
    monkeypatch.setattr(case.snapshots, "restore", slow)
    accepted = await previews.submit(scope, source, 1)
    await asyncio.wait_for(entered.wait(), 5)
    await FileApplication(case.instance, "survival", 1).update("config/000.txt", "changed while previewing")
    resume.set()
    await complete(case, accepted, success=False)
    assert "目标已变化" in case.tasks.get_task(accepted["task_id"]).error
    assert (target / "000.txt").read_text() == "changed while previewing"
    assert not list(previews.manager.base_dir.iterdir())


async def test_large_preview_fails_explicitly_and_releases_partial_pages(case, monkeypatch):
    from app.snapshots import previews as preview_module
    target, scope, source = await prepared(case, 3)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    monkeypatch.setattr(preview_module, "MAX_ACTION_BYTES", 1)
    accepted = await previews.submit(scope, source, 1)
    await complete(case, accepted, success=False)
    assert "缩小选择范围" in case.tasks.get_task(accepted["task_id"]).error
    assert (target / "000.txt").read_text() == "live value 0"
    assert not list(previews.manager.base_dir.iterdir())


async def test_bound_restore_rechecks_target_after_safety_before_writing(case, monkeypatch):
    target, scope, source = await prepared(case)
    previews = current_runtime().snapshot_previews
    assert previews is not None
    preview_id = (await complete(case, await previews.submit(scope, source, 1)))["preview_id"]
    saving, resume = asyncio.Event(), asyncio.Event()
    original = case.snapshots.create_snapshot

    async def slow_safety(*args, **kwargs):
        snapshot = await original(*args, **kwargs)
        saving.set()
        await resume.wait()
        return snapshot

    monkeypatch.setattr(case.snapshots, "create_snapshot", slow_safety)
    accepted = await case.commands.restore(scope, source, 1, preview_id=preview_id)
    await asyncio.wait_for(saving.wait(), 20)
    (target / "external.txt").write_text("external change after safety")
    resume.set()
    await complete(case, accepted, success=False)
    task = case.tasks.get_task(accepted["task_id"])
    assert task is not None and "目标已变化" in task.error
    record = await case.commands.store.get(accepted["restoration_id"])
    assert record is not None and record.safety_snapshot_id
    assert (target / "000.txt").read_text() == "live value 0"
    assert (target / "external.txt").read_text() == "external change after safety"
    operation = await case.journal.get(accepted["task_id"])
    assert operation is not None and not operation.data_changed and operation.writers_stopped


async def test_preview_includes_restoration_of_an_empty_file(case):
    target = case.data / "empty.txt"
    target.write_bytes(b"")
    scope = PathsScope(server_id="survival", paths=("empty.txt",))
    source = (await complete(case, await case.commands.create(scope, 1)))["snapshot"]["id"]
    target.unlink()
    previews = current_runtime().snapshot_previews
    assert previews is not None
    result = await complete(case, await previews.submit(scope, source, 1))
    actions = await previews.actions(result["preview_id"], 0, 100)
    assert any(action.item == str(target) and action.action == "restored" and action.size == 0 for action in actions.actions)
    assert not target.exists()
