"""
Comprehensive tests for BackgroundTaskManager.

Tests cover:
- Basic task submission and completion
- Task progress updates
- Task cancellation
- Task status transitions
- Task result handling
- Multiple concurrent tasks
- Task filtering
- Task removal and clearing
- Error handling
- Edge cases
"""

import asyncio

import pytest

from app.background_tasks import (
    BackgroundTask,
    BackgroundTaskManager,
    TaskProgress,
    TaskStatus,
    TaskType,
)
from app.errors import PublicOperationError


@pytest.fixture
async def task_manager():
    manager = BackgroundTaskManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


class TestBasicTaskSubmission:

    async def test_submit_global_task_without_server_id(self, task_manager):

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="global_archive",
            task_generator=simple_task(),
            server_id=None,
        )

        assert result.task.server_id is None

    async def test_task_completes_successfully(self, task_manager):
        started = asyncio.Event()
        finish = asyncio.Event()

        async def simple_task():
            yield TaskProgress(progress=50, message="Half done")
            started.set()
            await finish.wait()
            yield TaskProgress(progress=100, message="Complete")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=simple_task(),
            server_id="survival",
            cancellable=True,
        )
        task = task_manager.get_task(result.task_id)
        assert isinstance(result.task, BackgroundTask)
        assert result.task is task
        assert task.task_id == result.task_id
        assert task.server_id == "survival"
        assert task.cancellable is True
        assert task.status == TaskStatus.PENDING
        assert task.started_at is None
        assert task.ended_at is None
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            assert task.status == TaskStatus.RUNNING
            assert task.started_at is not None
            assert task.ended_at is None
            assert not result.awaitable.done()
            finish.set()
            task_result = await result.awaitable
            assert task_result.success is True
            assert task_result.error is None
            assert task.status == TaskStatus.COMPLETED
            assert task.ended_at is not None
        finally:
            finish.set()


class TestTaskProgressUpdates:

    @pytest.mark.parametrize("progress", [None, 25, -10, 150])
    async def test_progress_and_messages_are_observable(self, task_manager, progress):
        updated = asyncio.Event()
        finish = asyncio.Event()

        async def progress_task():
            yield TaskProgress(progress=progress, message="Processing")
            updated.set()
            await finish.wait()
            yield TaskProgress(progress=None if progress is None else 100, message="Complete")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=progress_task(),
        )

        try:
            await asyncio.wait_for(updated.wait(), timeout=5)
            task = task_manager.get_task(result.task_id)
            assert task.status == TaskStatus.RUNNING
            assert task.progress == progress
            assert task.message == "Processing"
            assert not result.awaitable.done()
            finish.set()
            await result.awaitable
            assert task.progress == (None if progress is None else 100)
            assert task.message == "Complete"
        finally:
            finish.set()

    @pytest.mark.parametrize("progress", [None, 0, 50, 150])
    async def test_completion_normalizes_only_numeric_progress(self, task_manager, progress):

        async def partial_progress_task():
            yield TaskProgress(progress=progress, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=partial_progress_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.progress == (None if progress is None else 100)


class TestTaskResultHandling:

    async def test_task_result_is_captured(self, task_manager):

        async def result_task():
            yield TaskProgress(progress=50, message="Processing...")
            yield TaskProgress(
                progress=100,
                message="Done",
                result={"filename": "output.7z", "size": 1024000},
            )

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=result_task(),
        )

        task_result = await result.awaitable

        assert task_result.success is True
        assert task_result.data == {"filename": "output.7z", "size": 1024000}

        task = task_manager.get_task(result.task_id)
        assert task.result == {"filename": "output.7z", "size": 1024000}

    async def test_task_result_from_last_yield(self, task_manager):

        async def multi_result_task():
            yield TaskProgress(progress=25, result={"step": 1})
            yield TaskProgress(progress=50, result={"step": 2})
            yield TaskProgress(progress=100, result={"step": 3, "final": True})

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=multi_result_task(),
        )

        task_result = await result.awaitable

        assert task_result.data == {"step": 3, "final": True}


class TestTaskCancellation:

    async def test_cancel_running_task(self, task_manager):
        cancel_event = asyncio.Event()

        async def long_task():
            for i in range(100):
                yield TaskProgress(progress=i, message=f"Step {i}")
                await asyncio.sleep(0.05)
                if i == 10:
                    cancel_event.set()

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=long_task(),
            cancellable=True,
        )

        await cancel_event.wait()
        success = await task_manager.cancel(result.task_id)
        assert success is True

        task_result = await result.awaitable

        assert task_result.success is False
        assert task_result.error == "已取消"

        task = task_manager.get_task(result.task_id)
        assert task.status == TaskStatus.CANCELLED

    async def test_cancel_non_cancellable_task_fails(self, task_manager):
        started = asyncio.Event()

        async def non_cancellable_task():
            started.set()
            yield TaskProgress(message="Running...")
            await asyncio.sleep(1)
            yield TaskProgress(message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="survival",
            task_generator=non_cancellable_task(),
            cancellable=False,
        )

        await started.wait()
        success = await task_manager.cancel(result.task_id)
        assert success is False

    async def test_cancel_completed_task_fails(self, task_manager):

        async def quick_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=quick_task(),
        )

        await result.awaitable

        success = await task_manager.cancel(result.task_id)
        assert success is False

    async def test_cancel_nonexistent_task_fails(self, task_manager):
        success = await task_manager.cancel("nonexistent_task_id")
        assert success is False


class TestTaskErrorHandling:

    async def test_task_failure_is_captured(self, task_manager):

        async def failing_task():
            yield TaskProgress(progress=50, message="Processing...")
            raise PublicOperationError("Something went wrong!")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=failing_task(),
        )

        task_result = await result.awaitable

        assert task_result.success is False
        assert "Something went wrong!" in task_result.error

        task = task_manager.get_task(result.task_id)
        assert task.status == TaskStatus.FAILED
        assert "Something went wrong!" in task.error
        assert task.ended_at is not None

    async def test_task_failure_preserves_progress(self, task_manager):

        async def failing_task():
            yield TaskProgress(progress=75, message="Almost there...")
            raise RuntimeError("Disk full!")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=failing_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.progress == 75


class TestTaskQueries:

    async def test_get_task_by_id(self, task_manager):

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=simple_task(),
        )

        task = task_manager.get_task(result.task_id)
        assert task is not None
        assert task.task_id == result.task_id

    async def test_get_nonexistent_task_returns_none(self, task_manager):
        task = task_manager.get_task("nonexistent_id")
        assert task is None

    async def test_get_all_tasks(self, task_manager):

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task1",
            task_generator=simple_task(),
        )
        task_manager.submit(
            task_type=TaskType.SERVER_REBUILD,
            name="task2",
            task_generator=simple_task(),
        )

        await asyncio.sleep(0.1)

        tasks = task_manager.get_all_tasks()
        assert len(tasks) == 2

    async def test_get_active_tasks(self, task_manager):
        started = asyncio.Event()

        async def quick_task():
            yield TaskProgress(progress=100, message="Done")

        async def slow_task():
            started.set()
            yield TaskProgress(progress=0, message="Starting...")
            await asyncio.sleep(10)
            yield TaskProgress(progress=100, message="Done")

        result1 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="quick_task",
            task_generator=quick_task(),
        )
        await result1.awaitable

        task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="slow_task",
            task_generator=slow_task(),
        )

        await started.wait()

        active_tasks = task_manager.get_active_tasks()
        assert len(active_tasks) == 1
        assert active_tasks[0].name == "slow_task"


class TestTaskRemoval:

    async def test_remove_completed_task(self, task_manager):

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=simple_task(),
        )

        await result.awaitable

        success = task_manager.remove_task(result.task_id)
        assert success is True

        task = task_manager.get_task(result.task_id)
        assert task is None

    async def test_remove_running_task_fails(self, task_manager):
        started = asyncio.Event()

        async def slow_task():
            started.set()
            yield TaskProgress(progress=0, message="Starting...")
            await asyncio.sleep(10)
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=slow_task(),
        )

        await started.wait()

        success = task_manager.remove_task(result.task_id)
        assert success is False

    async def test_remove_nonexistent_task_fails(self, task_manager):
        success = task_manager.remove_task("nonexistent_id")
        assert success is False

    async def test_clear_completed_tasks(self, task_manager):

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        async def failing_task():
            yield TaskProgress(progress=50, message="Processing...")
            raise ValueError("Error!")

        result1 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task1",
            task_generator=simple_task(),
        )
        result2 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task2",
            task_generator=failing_task(),
        )

        await result1.awaitable
        await result2.awaitable

        count = task_manager.clear_completed()
        assert count == 2

        tasks = task_manager.get_all_tasks()
        assert len(tasks) == 0

    async def test_clear_completed_preserves_running_tasks(self, task_manager):
        started = asyncio.Event()

        async def quick_task():
            yield TaskProgress(progress=100, message="Done")

        async def slow_task():
            started.set()
            yield TaskProgress(progress=0, message="Starting...")
            await asyncio.sleep(10)
            yield TaskProgress(progress=100, message="Done")

        result1 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="quick_task",
            task_generator=quick_task(),
        )
        await result1.awaitable

        task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="slow_task",
            task_generator=slow_task(),
        )

        await started.wait()

        count = task_manager.clear_completed()
        assert count == 1

        tasks = task_manager.get_all_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "slow_task"


class TestConcurrentTasks:

    async def test_multiple_concurrent_tasks(self, task_manager):
        entered = [asyncio.Event() for _ in range(3)]
        release = asyncio.Event()
        payloads = [{"name": "task1"}, {"name": "task2"}, {"name": "task3"}]

        async def gated_task(index):
            yield TaskProgress(progress=0, message="Working")
            entered[index].set()
            await release.wait()
            yield TaskProgress(progress=100, message="Done", result=payloads[index])

        receipts = [
            task_manager.submit(
                task_type=TaskType.ARCHIVE_CREATE,
                name=payload["name"],
                task_generator=gated_task(index),
            )
            for index, payload in enumerate(payloads)
        ]
        try:
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered)), timeout=5)
            assert len({receipt.task_id for receipt in receipts}) == 3
            for receipt in receipts:
                assert not receipt.awaitable.done()
                assert task_manager.get_task(receipt.task_id).status == TaskStatus.RUNNING
            release.set()
            results = await asyncio.gather(*(receipt.awaitable for receipt in receipts))
            for receipt, result, payload in zip(receipts, results, payloads, strict=True):
                assert result.success is True
                assert result.data == payload
                task = task_manager.get_task(receipt.task_id)
                assert task.result == payload
                assert task.name == payload["name"]
                assert task.status == TaskStatus.COMPLETED
        finally:
            release.set()
            await task_manager.shutdown()



class TestTaskTypes:

    @pytest.mark.parametrize(
        "task_type",
        [
            TaskType.ARCHIVE_CREATE,
            TaskType.ARCHIVE_EXTRACT,
            TaskType.SERVER_REBUILD,
        ],
    )
    async def test_task_type_metadata_is_retained(self, task_manager, task_type):

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=task_type,
            name="test_task",
            task_generator=simple_task(),
        )

        task_result = await result.awaitable

        assert task_result.success is True
        assert result.task.task_type == task_type


class TestEdgeCases:

    async def test_empty_task_generator(self, task_manager):

        async def empty_task():
            return
            yield

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="empty_task",
            task_generator=empty_task(),
        )

        task_result = await result.awaitable

        assert task_result.success is True
        task = task_manager.get_task(result.task_id)
        assert task.status == TaskStatus.COMPLETED

    async def test_task_with_unicode_name(self, task_manager):

        async def simple_task():
            yield TaskProgress(progress=100, message="完成！")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="测试任务_🎮_世界备份",
            task_generator=simple_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.name == "测试任务_🎮_世界备份"
        assert task.message == "完成！"


class TestTasksByServerIdAndGetFuture:

    async def test_get_tasks_by_server_id_filters_correctly(self, task_manager):
        started = asyncio.Event()

        async def slow_task():
            started.set()
            yield TaskProgress(progress=0, message="working")
            await asyncio.sleep(5)
            yield TaskProgress(progress=100, message="done")

        async def quick_task():
            yield TaskProgress(progress=100, message="done")

        task_manager.submit(
            task_type=TaskType.ARCHIVE_EXTRACT,
            name="slow-a",
            task_generator=slow_task(),
            server_id="server-a",
        )
        result_done = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="finished-a",
            task_generator=quick_task(),
            server_id="server-a",
        )
        task_manager.submit(
            task_type=TaskType.ARCHIVE_EXTRACT,
            name="slow-b",
            task_generator=slow_task(),
            server_id="server-b",
        )

        await result_done.awaitable  # one task is now completed
        await started.wait()

        a_tasks = task_manager.get_tasks_by_server_id("server-a")
        # Only the still-running one for server-a should be returned
        assert {t.name for t in a_tasks} == {"slow-a"}

        b_tasks = task_manager.get_tasks_by_server_id("server-b")
        assert {t.name for t in b_tasks} == {"slow-b"}

        # Unknown server
        assert task_manager.get_tasks_by_server_id("nope") == []

    async def test_get_future_returns_submitted_future(self, task_manager):
        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="future-test",
            task_generator=simple_task(),
        )

        future = task_manager.get_future(result.task_id)
        assert future is not None
        assert future is result.awaitable

    async def test_get_future_returns_none_for_unknown_task(self, task_manager):
        assert task_manager.get_future("nope") is None


class TestAwaitableSemantics:

    async def test_awaitable_resolves_after_completion(self, task_manager):
        completed = False

        async def tracking_task():
            nonlocal completed
            yield TaskProgress(progress=50, message="Working...")
            await asyncio.sleep(0.1)
            yield TaskProgress(progress=100, message="Done")
            completed = True

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="tracking_task",
            task_generator=tracking_task(),
        )

        await result.awaitable
        assert completed is True

    async def test_multiple_awaits_on_same_future(self, task_manager):

        async def simple_task():
            yield TaskProgress(progress=100, message="Done", result={"value": 42})

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="multi_await",
            task_generator=simple_task(),
        )

        task_result1 = await result.awaitable
        task_result2 = await result.awaitable

        assert task_result1.success is True
        assert task_result2.success is True
        assert task_result1.data == task_result2.data
