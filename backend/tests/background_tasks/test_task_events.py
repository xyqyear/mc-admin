import asyncio
import json
from contextlib import aclosing
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from starlette.types import Message, Scope

from app.auth.schemas import UserPublic
from app.background_tasks import (
    BackgroundTask,
    BackgroundTaskManager,
    TaskProgress,
    TaskStatus,
    TaskType,
)
from app.background_tasks import events as task_events
from app.dependencies import get_current_user
from app.errors import PublicOperationError
from app.operations.finalization import finalize
from app.routers.tasks import router
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def manager():
    manager = BackgroundTaskManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


async def read_event(stream):
    frame = await asyncio.wait_for(anext(stream), 2)
    assert frame.startswith(b"data: ") and frame.endswith(b"\n\n")
    return json.loads(frame[6:])


@pytest.mark.parametrize("failed", [False, True])
async def test_progress_and_terminal_follow_worker_finalization(manager, failed):
    ready, release, cleaning, settled = (asyncio.Event() for _ in range(4))
    result = {"output": "retained detail"}

    async def work():
        try:
            yield TaskProgress(progress=25, message="正在执行", result=result)
            ready.set()
            await release.wait()
            yield TaskProgress(progress=100, message="写入已完成", result=result)
            if failed:
                raise PublicOperationError("任务未完成")
        finally:
            cleaning.set()
            await settled.wait()

    async with aclosing(manager.events()) as stream:
        assert await read_event(stream) == {"type": "snapshot", "tasks": []}
        accepted = manager.submit(TaskType.ARCHIVE_CREATE, "测试任务", work())
        try:
            await ready.wait()
            update = await read_event(stream)
            assert update["type"] == "upsert"
            assert update["task"]["task_id"] == accepted.task_id
            assert update["task"]["status"] == "running"
            assert update["task"]["progress"] == 25
            assert "result" not in update["task"]
            release.set()
            await cleaning.wait()
            update = await read_event(stream)
            assert update["task"]["progress"] == 100
            assert update["task"]["status"] == "running"
            assert not accepted.awaitable.done()
            settled.set()
            assert (await accepted.awaitable).success is not failed
            terminal = await read_event(stream)
            assert terminal["task"]["status"] == ("failed" if failed else "completed")
            assert terminal["task"]["error"] == ("任务未完成" if failed else None)
            assert terminal["task"]["ended_at"] is not None
            assert "result" not in terminal["task"]
            detail = await manager.get_task_detail(accepted.task_id)
            assert detail is not None and detail.result == result
            assert not manager.update_progress(accepted.task_id, TaskProgress(progress=0))
            assert manager.remove_task(accepted.task_id)
            assert await read_event(stream) == {"type": "remove", "task_id": accepted.task_id}
        finally:
            release.set()
            settled.set()


@pytest.mark.parametrize("cancel", [False, True])
async def test_disconnect_and_reconnect_do_not_own_worker_or_its_cleanup(manager, cancel):
    ready, release, cleaning, settled = (asyncio.Event() for _ in range(4))

    async def work():
        try:
            ready.set()
            await release.wait()
            yield TaskProgress(progress=None, result={"retained": True})
        finally:
            cleaning.set()
            await finalize(settled.wait())

    accepted = manager.submit(TaskType.ARCHIVE_CREATE, "独立执行", work())
    try:
        await ready.wait()
        async with aclosing(manager.events()) as first:
            snapshot = await read_event(first)
            assert snapshot["tasks"][0]["progress"] is None
            assert snapshot["tasks"][0]["server_id"] is None
            assert snapshot["tasks"][0]["error"] is None
            assert manager._events.subscriber_count == 1
        assert manager._events.subscriber_count == 0
        assert not accepted.task.cancel_requested and not accepted.awaitable.done()
        async with aclosing(manager.events()) as second:
            assert (await read_event(second))["tasks"][0]["status"] == "running"
            if cancel:
                assert await manager.cancel(accepted.task_id)
                assert await manager.cancel(accepted.task_id)
            else:
                release.set()
            await cleaning.wait()
            assert not accepted.awaitable.done()
            update = await read_event(second)
            assert update["task"]["status"] == "running"
            if cancel:
                assert update["task"]["message"] == "正在取消，等待清理完成"
            settled.set()
            assert (await accepted.awaitable).success is not cancel
            assert (await read_event(second))["task"]["status"] == ("cancelled" if cancel else "completed")
    finally:
        release.set()
        settled.set()


async def test_slow_subscriber_resynchronizes_current_state_without_delaying_another(manager):
    for index in range(task_events.MAX_PENDING_TASKS + 2):
        manager._tasks[str(index)] = BackgroundTask(
            task_id=str(index), task_type=TaskType.ARCHIVE_CREATE,
            name=f"任务 {index}", status=TaskStatus.RUNNING,
            result={"large": "excluded" * 1000},
        )
    async with aclosing(manager.events()) as slow, aclosing(manager.events()) as fast:
        await read_event(slow)
        await read_event(fast)
        for task_id in manager._tasks:
            manager.update_progress(task_id, TaskProgress(progress=50, message="最新状态"))
            frame = await read_event(fast)
            assert frame["type"] == "upsert" and frame["task"]["task_id"] == task_id
            assert "result" not in frame["task"]
            assert all(len(subscription.pending) <= 256 for subscription in manager._events._subscriptions)
        manager._tasks["0"].status = TaskStatus.COMPLETED
        assert manager.remove_task("0")
        assert await read_event(fast) == {"type": "remove", "task_id": "0"}
        snapshot = await read_event(slow)
        assert snapshot["type"] == "snapshot"
        assert {task["task_id"] for task in snapshot["tasks"]} == set(manager._tasks)
        assert all(task["progress"] == 50 and "result" not in task for task in snapshot["tasks"])


async def test_result_only_updates_notify_and_repeated_ids_coalesce(manager):
    manager._tasks["same"] = BackgroundTask(task_id="same", task_type=TaskType.ARCHIVE_CREATE, name="当前任务")
    async with aclosing(manager.events()) as stream:
        await read_event(stream)
        assert manager.update_progress("same", TaskProgress(result={"stage": "palette"}))
        frame = await read_event(stream)
        assert frame["type"] == "upsert" and "result" not in frame["task"]
        for progress in range(1000):
            manager.update_progress("same", TaskProgress(progress=progress))
        assert all(len(subscription.pending) == 1 for subscription in manager._events._subscriptions)
        frame = await read_event(stream)
        assert frame["type"] == "upsert" and frame["task"]["progress"] == 999
        task = manager.get_task("same")
        assert task is not None and task.result == {"stage": "palette"}
        assert not manager.update_progress("missing", TaskProgress(progress=0))


async def test_idle_heartbeat_does_not_poll_tasks(monkeypatch):
    get_task, get_tasks = Mock(return_value=None), Mock(return_value=[])
    feed = task_events.TaskEventStream(get_task, get_tasks)
    monkeypatch.setattr(task_events, "HEARTBEAT_SECONDS", 0.001)
    async with aclosing(feed.events()) as stream:
        assert await read_event(stream) == {"type": "snapshot", "tasks": []}
        assert await asyncio.wait_for(anext(stream), 2) == b": keepalive\n\n"
        assert get_tasks.call_count == 1
        get_task.assert_not_called()
    assert feed.subscriber_count == 0


async def test_shutdown_wakes_and_closes_idle_subscriptions(manager):
    async with aclosing(manager.events()) as first, aclosing(manager.events()) as second:
        await read_event(first)
        await read_event(second)
        pending = [asyncio.create_task(anext(stream)) for stream in (first, second)]
        await manager.shutdown()
        for observer in pending:
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(observer, 2)
        assert manager._events.subscriber_count == 0


@pytest.mark.parametrize("authenticated", [False, True])
async def test_events_route_authentication_stream_headers_and_disconnect_cleanup(manager, monkeypatch, authenticated):
    application = FastAPI()
    application.include_router(router)
    set_runtime_resource(monkeypatch, "task_manager", manager)
    if authenticated:
        application.dependency_overrides[get_current_user] = lambda: UserPublic(
            id=1, username="observer", created_at=datetime.now(UTC),
        )
    messages: list[Message] = []
    disconnected = asyncio.Event()

    async def receive() -> Message:
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)
        if message["type"] == "http.response.body":
            disconnected.set()

    scope: Scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": "/tasks/events", "raw_path": b"/tasks/events", "query_string": b"", "headers": [],
    }
    await asyncio.wait_for(application(scope, receive, send), 2)
    assert messages[0]["status"] == (200 if authenticated else 401)
    if authenticated:
        headers = dict(messages[0]["headers"])
        assert headers[b"content-type"].startswith(b"text/event-stream")
        assert headers[b"cache-control"] == b"no-cache"
        assert headers[b"x-accel-buffering"] == b"no"
        assert json.loads(messages[1]["body"][6:]) == {"type": "snapshot", "tasks": []}
    assert manager._events.subscriber_count == 0
