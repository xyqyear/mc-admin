import asyncio
import json
from contextlib import aclosing
from dataclasses import replace

import pytest

from app.background_tasks import BackgroundTaskManager
from app.operations.changes import OperationChangeFeed
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)


async def read_event(stream):
    frame = await asyncio.wait_for(anext(stream), 2)
    return json.loads(frame[6:])


def spec(operation_id):
    return OperationSpec(
        "archive_create", (ResourceReference("archive"),), origin="task",
        operation_id=operation_id, legacy_id=operation_id, name="归档任务",
    )


async def test_operation_cursor_replays_commits_and_disconnect_unsubscribes(journal):
    manager = BackgroundTaskManager(journal)
    cursor = journal.changes.read().next_cursor
    await journal.accept(spec("accepted"))
    async with aclosing(manager.events(cursor)) as stream:
        assert (await read_event(stream))["type"] == "snapshot"
        changes = (await read_event(stream))["changes"]
        assert not changes["reset_required"]
        assert [(item["operation_id"], item["state"]) for item in changes["items"]] == [("accepted", "queued")]
        assert len(journal.changes._listeners) == 1
        await journal.finish("accepted", OperationState.SUCCEEDED, writers_stopped=True)
        terminal = (await read_event(stream))["changes"]
        assert terminal["items"][0]["state"] == "succeeded"
        assert terminal["active_count"] == 0
    assert len(journal.changes._listeners) == 0
    assert manager._events.subscriber_count == 0
    async with aclosing(manager.events(terminal["next_cursor"])) as stream:
        await read_event(stream)
        assert (await read_event(stream))["changes"]["items"] == []
    await manager.shutdown()


async def test_operation_paging_preserves_commits_after_pinned_final_page(journal):
    record = await journal.accept(spec("seed"))
    journal.changes = OperationChangeFeed()
    cursor = journal.changes.read().next_cursor
    for index in range(201):
        journal.changes.publish(replace(record, operation_id=str(index)))
    manager = BackgroundTaskManager(journal)
    async with aclosing(manager.events(cursor)) as stream:
        await read_event(stream)
        first = (await read_event(stream))["changes"]
        assert len(first["items"]) == 200 and first["has_more"]
        journal.changes.publish(replace(record, operation_id="new-after-head"))
        last_page = (await read_event(stream))["changes"]
        assert [item["operation_id"] for item in last_page["items"]] == ["200"]
        assert not last_page["has_more"]
        following = (await read_event(stream))["changes"]
        assert [item["operation_id"] for item in following["items"]] == ["new-after-head"]
    await manager.shutdown()


@pytest.mark.parametrize("reset", [False, True])
async def test_operation_eviction_or_epoch_reset_wakes_current_stream(journal, reset):
    record = await journal.accept(spec("seed"))
    journal.changes = OperationChangeFeed(max_records=2)
    manager = BackgroundTaskManager(journal)
    async with aclosing(manager.events()) as stream:
        await read_event(stream)
        assert (await read_event(stream))["changes"]["reset_required"]
        if reset:
            journal.changes.reset()
        else:
            for index in range(3):
                journal.changes.publish(replace(record, operation_id=str(index)))
        changes = (await read_event(stream))["changes"]
        assert changes["reset_required"] and changes["items"] == []
    await manager.shutdown()


async def test_restored_history_does_not_claim_unloaded_result_is_null(journal):
    await journal.accept(spec("retained"))
    await journal.save_task_result("retained", {"output": "preserved"})
    record = await journal.finish("retained", OperationState.SUCCEEDED, writers_stopped=True)
    manager = BackgroundTaskManager(journal)
    manager.restore_history([record])
    async with aclosing(manager.events()) as stream:
        task = (await read_event(stream))["tasks"][0]
        assert task["status"] == "completed"
        assert not task["result_included"] and task["result"] is None
        detail = await manager.get_task_detail("retained")
        assert detail is not None and detail.result == {"output": "preserved"}
    await manager.shutdown()


async def test_provider_failure_releases_operation_listener(journal):
    manager = BackgroundTaskManager(journal)

    async def failing_index(_domain):
        raise RuntimeError("synthetic index failure")

    async with aclosing(manager.events(get_index=failing_index)) as stream:
        with pytest.raises(RuntimeError, match="synthetic index failure"):
            await read_event(stream)
    assert manager._events.subscriber_count == 0
    assert not journal.changes._listeners
    await manager.shutdown()


async def test_shutdown_releases_journal_listener_while_observer_is_suspended(journal):
    manager = BackgroundTaskManager(journal)
    async with aclosing(manager.events()) as stream:
        await read_event(stream)
        assert journal.changes._listeners
        await manager.shutdown()
        assert not journal.changes._listeners
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
