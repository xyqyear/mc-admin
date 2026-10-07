from dataclasses import replace
from unittest.mock import Mock

import pytest
from sqlalchemy import event

from app.operations.changes import OperationChangeFeed
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ProcessIdentity,
    ResourceReference,
)

RESOURCE = ResourceReference("files", "survival", 12, "world")


def spec(operation_id: str) -> OperationSpec:
    return OperationSpec("file_write", (RESOURCE,), operation_id=operation_id)


async def test_old_operation_completion_and_partial_failure_are_incremental(journal):
    await journal.accept(spec("old"))
    await journal.start("old")
    initial = journal.changes.read()
    assert initial.reset_required and initial.items == () and initial.active_count == 1
    await journal.accept(spec("newer"))
    await journal.phase("old", "write", changed=True)
    await journal.finish("old", OperationState.FAILED, writers_stopped=True)

    changes = journal.changes.read(initial.next_cursor)
    assert not changes.reset_required and not changes.has_more and changes.active_count == 1
    assert [(item.operation_id, item.state) for item in changes.items] == [
        ("newer", "queued"), ("old", "running"), ("old", "failed"),
    ]
    assert changes.items[-1].data_changed and changes.items[-1].resources == (RESOURCE,)
    assert len({item.sequence for item in changes.items}) == 3
    assert journal.changes.read(initial.next_cursor).items == changes.items
    idle = journal.changes.read(changes.next_cursor)
    assert idle.items == () and not idle.reset_required


async def test_progress_and_task_results_do_not_emit_refresh_notifications(journal):
    await journal.accept(spec("progress"))
    cursor = journal.changes.read().next_cursor
    await journal.start("progress")
    await journal.phase("progress", "copying")
    process = ProcessIdentity(123, 123, 456, "synthetic-boot", 12, 34)
    await journal.register_process("progress", process)
    await journal.phase("progress", "stopping", state=OperationState.CANCELLING)
    await journal.process_stopped("progress", process.pid, process.start_ticks)
    await journal.save_task_result("progress", {"private_payload": "x" * 100_000})
    unchanged = journal.changes.read(cursor)
    assert unchanged.items == () and unchanged.active_count == 1
    await journal.finish("progress", OperationState.CANCELLED, writers_stopped=True)
    final = journal.changes.read(cursor)
    assert [(item.operation_id, item.state) for item in final.items] == [("progress", "cancelled")]
    assert final.active_count == 0


async def test_resource_notifications_are_immutable_and_terminal_recovery_notifies(journal):
    initial = journal.changes.read()
    await journal.accept(OperationSpec("server_create", (ResourceReference("files", path="survival"),), operation_id="create"))
    await journal.bind_created_server("create", "survival", 12)
    await journal.finish("create", OperationState.INTERRUPTED, writers_stopped=False)
    changes = journal.changes.read(initial.next_cursor)
    assert changes.items[0].resources == (ResourceReference("files", path="survival"),)
    assert changes.items[1].resources == (ResourceReference("server", "survival", 12),)
    assert changes.items[-1].state == "interrupted" and changes.active_count == 0
    await journal.resolve("create", actor_id=41, writers_stopped=True)
    recovered = journal.changes.read(changes.next_cursor)
    assert len(recovered.items) == 1 and recovered.items[0].state == "interrupted"


async def test_paging_pins_current_batch_and_preserves_new_commits(journal):
    initial = journal.changes.read()
    for operation_id in ("one", "two", "three"):
        await journal.accept(spec(operation_id))
    first = journal.changes.read(initial.next_cursor, limit=1)
    assert [item.operation_id for item in first.items] == ["one"] and first.has_more
    await journal.accept(spec("four"))
    second = journal.changes.read(first.next_cursor, limit=1)
    third = journal.changes.read(second.next_cursor, limit=1)
    assert [item.operation_id for item in second.items] == ["two"] and second.has_more
    assert [item.operation_id for item in third.items] == ["three"] and not third.has_more
    following = journal.changes.read(third.next_cursor)
    assert [item.operation_id for item in following.items] == ["four"] and not following.has_more


async def test_eviction_between_pages_requires_reset_without_losing_business_history(journal):
    journal.changes = OperationChangeFeed(max_records=2)
    initial = journal.changes.read()
    await journal.accept(spec("one"))
    await journal.accept(spec("two"))
    page = journal.changes.read(initial.next_cursor, limit=1)
    await journal.accept(spec("three"))
    await journal.accept(spec("four"))
    expired = journal.changes.read(page.next_cursor)
    assert expired.reset_required and expired.items == () and expired.active_count == 4
    assert journal.changes.read(expired.next_cursor).items == ()
    assert {record.operation_id for record in await journal.list()} == {"one", "two", "three", "four"}


async def test_byte_capacity_and_oversized_entry_reset_existing_readers(journal):
    journal.changes = OperationChangeFeed(max_records=100, max_bytes=700)
    initial = journal.changes.read()
    await journal.accept(spec("one"))
    await journal.accept(spec("two"))
    await journal.accept(spec("three"))
    assert journal.changes.read(initial.next_cursor).reset_required
    current = journal.changes.read()
    await journal.accept(replace(spec("large"), resources=(replace(RESOURCE, path="a" * 1000),)))
    oversized = journal.changes.read(current.next_cursor)
    assert oversized.reset_required and oversized.items == () and oversized.active_count == 4
    await journal.finish("large", OperationState.SUCCEEDED, writers_stopped=True)
    assert journal.changes.read().active_count == 3
    assert (await journal.get("large")).state == OperationState.SUCCEEDED


@pytest.mark.parametrize("cursor", ["", "broken", "a" * 1000, "💥", "!invalid!"])
async def test_malformed_cursor_returns_current_reset_position(journal, cursor):
    await journal.accept(spec("active"))
    result = journal.changes.read(cursor)
    assert result.reset_required and result.items == () and result.next_cursor
    assert not journal.changes.read(result.next_cursor).reset_required


async def test_future_cursor_and_new_instance_require_reset(journal):
    await journal.accept(spec("active"))
    future = journal.changes._cursor(2)
    assert journal.changes.read(future).reset_required
    original = journal.changes.read()
    reopened = OperationJournal(journal.session_factory)
    await reopened.initialize_changes()
    reset = reopened.changes.read(original.next_cursor)
    assert reset.reset_required and reset.items == () and reset.active_count == 1
    await reopened.recover_interrupted("active", writers_stopped=True, blocked_reason=None)
    recovered = reopened.changes.read(reset.next_cursor)
    assert [(item.operation_id, item.state) for item in recovered.items] == [("active", "interrupted")]
    assert recovered.active_count == 0
    assert journal.changes.read(original.next_cursor).items == ()


async def test_notification_is_visible_only_after_successful_commit(journal):
    await journal.accept(spec("commit"))
    cursor = journal.changes.read().next_cursor
    engine = journal.session_factory.kw["bind"]
    checked = []

    def check_before_commit(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("UPDATE operation_journal"):
            checked.append(journal.changes.read(cursor).items)

    event.listen(engine.sync_engine, "after_cursor_execute", check_before_commit)
    try:
        await journal.finish("commit", OperationState.SUCCEEDED, writers_stopped=True)
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", check_before_commit)
    assert checked == [()]
    assert journal.changes.read(cursor).items[0].state == "succeeded"
    reopened = OperationJournal(journal.session_factory)
    persisted = await reopened.get("commit")
    assert persisted is not None and persisted.state == OperationState.SUCCEEDED


async def test_rollback_emits_no_notification_and_keeps_active_count(journal):
    await journal.accept(spec("rollback"))
    cursor = journal.changes.read().next_cursor
    engine = journal.session_factory.kw["bind"]

    def fail_update(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("UPDATE operation_journal"):
            raise OSError("synthetic write failure")

    event.listen(engine.sync_engine, "after_cursor_execute", fail_update)
    try:
        with pytest.raises(OSError, match="synthetic write failure"):
            await journal.finish("rollback", OperationState.SUCCEEDED, writers_stopped=True)
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", fail_update)
    unchanged = journal.changes.read(cursor)
    assert unchanged.items == () and unchanged.active_count == 1
    assert (await journal.get("rollback")).state == OperationState.QUEUED


async def test_notification_failure_resets_observers_without_changing_committed_result(journal, monkeypatch):
    await journal.accept(spec("notify"))
    cursor = journal.changes.read().next_cursor
    monkeypatch.setattr(journal.changes, "publish", Mock(side_effect=OSError("synthetic notification failure")))
    monkeypatch.setattr("app.operations.journal.log_safe_error", Mock())
    finished = await journal.finish("notify", OperationState.SUCCEEDED, writers_stopped=True)
    assert finished.state == OperationState.SUCCEEDED
    assert (await journal.get("notify")).state == OperationState.SUCCEEDED
    reset = journal.changes.read(cursor)
    assert reset.reset_required and reset.items == () and reset.active_count == 0


async def test_runtime_shutdown_discards_notifications_and_active_tracking(journal, isolated_runtime):
    isolated_runtime.journal = journal
    await journal.accept(spec("closed"))
    cursor = journal.changes.read().next_cursor
    await journal.finish("closed", OperationState.CANCELLED, writers_stopped=True)
    await isolated_runtime.close()
    result = journal.changes.read(cursor)
    assert result.reset_required and result.items == () and result.active_count == 0
