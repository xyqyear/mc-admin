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


@pytest.fixture
def task_manager():
    """Create a fresh BackgroundTaskManager for each test."""
    return BackgroundTaskManager()


class TestBasicTaskSubmission:
    """Test basic task submission functionality."""

    async def test_submit_task_returns_submit_result(self, task_manager):
        """Test that submit returns a SubmitResult with correct fields."""

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test_archive.7z",
            task_generator=simple_task(),
            server_id="survival",
            cancellable=True,
        )

        assert result.task_id is not None
        assert result.task is not None
        assert result.awaitable is not None
        assert isinstance(result.task, BackgroundTask)

    async def test_submit_task_creates_task_with_correct_fields(self, task_manager):
        """Test that submitted task has correct initial fields."""

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.SNAPSHOT_CREATE,
            name="backup_snapshot",
            task_generator=simple_task(),
            server_id="creative",
            cancellable=False,
        )

        task = result.task
        assert task.task_type == TaskType.SNAPSHOT_CREATE
        assert task.name == "backup_snapshot"
        assert task.server_id == "creative"
        assert task.cancellable is False
        assert task.created_at is not None

    async def test_submit_global_task_without_server_id(self, task_manager):
        """Test submitting a global task (server_id=None)."""

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
        """Test that a task completes and returns success."""

        async def simple_task():
            yield TaskProgress(progress=50, message="Half done")
            yield TaskProgress(progress=100, message="Complete")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=simple_task(),
        )

        task_result = await result.awaitable
        assert task_result.success is True
        assert task_result.error is None

    async def test_task_status_transitions_to_completed(self, task_manager):
        """Test that task status transitions from PENDING to RUNNING to COMPLETED."""

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=simple_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.started_at is not None
        assert task.ended_at is not None


class TestTaskProgressUpdates:
    """Test task progress update functionality."""

    async def test_progress_updates_are_reflected_in_task(self, task_manager):
        """Test that progress updates are reflected in the task object."""

        async def progress_task():
            for i in range(0, 101, 25):
                yield TaskProgress(progress=i, message=f"Progress: {i}%")
                await asyncio.sleep(0.01)

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=progress_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.progress == 100

    async def test_message_updates_are_reflected_in_task(self, task_manager):
        """Test that message updates are reflected in the task object."""

        async def message_task():
            yield TaskProgress(message="Starting...")
            yield TaskProgress(message="Processing...")
            yield TaskProgress(message="Finalizing...")
            yield TaskProgress(message="Complete!")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=message_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.message == "Complete!"

    async def test_task_without_progress_stays_none(self, task_manager):
        """Test that tasks without progress keep progress as None."""

        async def no_progress_task():
            yield TaskProgress(message="Starting server...")
            yield TaskProgress(message="Server started!")

        result = task_manager.submit(
            task_type=TaskType.SERVER_START,
            name="survival",
            task_generator=no_progress_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.progress is None

    async def test_progress_set_to_100_on_completion_if_had_progress(
        self, task_manager
    ):
        """Test that progress is set to 100 on completion if task had progress."""

        async def partial_progress_task():
            yield TaskProgress(progress=50, message="Half done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="test.7z",
            task_generator=partial_progress_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.progress == 100


class TestTaskResultHandling:
    """Test task result handling functionality."""

    async def test_task_result_is_captured(self, task_manager):
        """Test that task result data is captured correctly."""

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
        """Test that only the last yielded result is kept."""

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
    """Test task cancellation functionality."""

    async def test_cancel_running_task(self, task_manager):
        """Test cancelling a running task."""
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
        """Test that cancelling a non-cancellable task fails."""
        started = asyncio.Event()

        async def non_cancellable_task():
            started.set()
            yield TaskProgress(message="Running...")
            await asyncio.sleep(1)
            yield TaskProgress(message="Done")

        result = task_manager.submit(
            task_type=TaskType.SERVER_START,
            name="survival",
            task_generator=non_cancellable_task(),
            cancellable=False,
        )

        await started.wait()
        success = await task_manager.cancel(result.task_id)
        assert success is False

    async def test_cancel_completed_task_fails(self, task_manager):
        """Test that cancelling a completed task fails."""

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
        """Test that cancelling a nonexistent task fails."""
        success = await task_manager.cancel("nonexistent_task_id")
        assert success is False


class TestTaskErrorHandling:
    """Test task error handling functionality."""

    async def test_task_failure_is_captured(self, task_manager):
        """Test that task failures are captured correctly."""

        async def failing_task():
            yield TaskProgress(progress=50, message="Processing...")
            raise ValueError("Something went wrong!")

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
        """Test that task failure preserves the last progress value."""

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
    """Test task query functionality."""

    async def test_get_task_by_id(self, task_manager):
        """Test getting a task by ID."""

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
        """Test that getting a nonexistent task returns None."""
        task = task_manager.get_task("nonexistent_id")
        assert task is None

    async def test_get_all_tasks(self, task_manager):
        """Test getting all tasks."""

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task1",
            task_generator=simple_task(),
        )
        task_manager.submit(
            task_type=TaskType.SNAPSHOT_CREATE,
            name="task2",
            task_generator=simple_task(),
        )

        await asyncio.sleep(0.1)

        tasks = task_manager.get_all_tasks()
        assert len(tasks) == 2

    async def test_get_active_tasks(self, task_manager):
        """Test getting only active (pending/running) tasks."""
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
    """Test task removal functionality."""

    async def test_remove_completed_task(self, task_manager):
        """Test removing a completed task."""

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
        """Test that removing a running task fails."""
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
        """Test that removing a nonexistent task fails."""
        success = task_manager.remove_task("nonexistent_id")
        assert success is False

    async def test_clear_completed_tasks(self, task_manager):
        """Test clearing all completed tasks."""

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
        """Test that clearing completed tasks preserves running tasks."""
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
    """Test concurrent task handling."""

    async def test_multiple_concurrent_tasks(self, task_manager):
        """Test running multiple tasks concurrently."""

        async def task_with_delay(delay: float, name: str):
            yield TaskProgress(progress=0, message=f"{name} starting")
            await asyncio.sleep(delay)
            yield TaskProgress(
                progress=100, message=f"{name} done", result={"name": name}
            )

        result1 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task1",
            task_generator=task_with_delay(0.1, "task1"),
        )
        result2 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task2",
            task_generator=task_with_delay(0.1, "task2"),
        )
        result3 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task3",
            task_generator=task_with_delay(0.1, "task3"),
        )

        task_results = await asyncio.gather(
            result1.awaitable,
            result2.awaitable,
            result3.awaitable,
        )

        for task_result in task_results:
            assert task_result.success is True

        tasks = task_manager.get_all_tasks()
        assert len(tasks) == 3
        assert all(t.status == TaskStatus.COMPLETED for t in tasks)

    async def test_tasks_have_unique_ids(self, task_manager):
        """Test that each task gets a unique ID."""

        async def simple_task():
            yield TaskProgress(progress=100, message="Done")

        result1 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task1",
            task_generator=simple_task(),
        )
        result2 = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="task2",
            task_generator=simple_task(),
        )

        task_ids = [result1.task_id, result2.task_id]
        assert len(task_ids) == len(set(task_ids))


class TestTaskTypes:
    """Test different task types."""

    @pytest.mark.parametrize(
        "task_type",
        [
            TaskType.ARCHIVE_CREATE,
            TaskType.ARCHIVE_EXTRACT,
            TaskType.SNAPSHOT_CREATE,
            TaskType.SNAPSHOT_RESTORE,
            TaskType.SERVER_START,
            TaskType.SERVER_STOP,
            TaskType.SERVER_RESTART,
        ],
    )
    async def test_all_task_types_work(self, task_manager, task_type):
        """Test that all task types can be submitted and completed."""

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
    """Test edge cases and boundary conditions."""

    async def test_empty_task_generator(self, task_manager):
        """Test task with empty generator (no yields)."""

        async def empty_task():
            return
            yield  # noqa: B901 - This is intentionally unreachable for testing

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="empty_task",
            task_generator=empty_task(),
        )

        task_result = await result.awaitable

        assert task_result.success is True
        task = task_manager.get_task(result.task_id)
        assert task.status == TaskStatus.COMPLETED

    async def test_task_with_zero_progress(self, task_manager):
        """Test task that only yields zero progress."""

        async def zero_progress_task():
            yield TaskProgress(progress=0, message="Starting...")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="zero_progress",
            task_generator=zero_progress_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.progress == 100

    async def test_task_with_negative_progress(self, task_manager):
        """Test task with negative progress value (edge case)."""

        async def negative_progress_task():
            yield TaskProgress(progress=-10, message="Invalid progress")
            yield TaskProgress(progress=100, message="Done")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="negative_progress",
            task_generator=negative_progress_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.status == TaskStatus.COMPLETED

    async def test_task_with_progress_over_100(self, task_manager):
        """Test task with progress over 100 (edge case)."""

        async def over_100_progress_task():
            yield TaskProgress(progress=150, message="Over 100%")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="over_100",
            task_generator=over_100_progress_task(),
        )

        await result.awaitable

        task = task_manager.get_task(result.task_id)
        assert task.progress == 100

    async def test_rapid_progress_updates(self, task_manager):
        """Test task with many rapid progress updates."""

        async def rapid_updates_task():
            for i in range(1000):
                yield TaskProgress(progress=i / 10, message=f"Step {i}")

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="rapid_updates",
            task_generator=rapid_updates_task(),
        )

        task_result = await result.awaitable

        assert task_result.success is True
        task = task_manager.get_task(result.task_id)
        assert task.status == TaskStatus.COMPLETED

    async def test_task_with_unicode_name(self, task_manager):
        """Test task with unicode characters in name."""

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

    async def test_task_with_large_result_data(self, task_manager):
        """Test task with large result data."""
        large_data = {"items": [f"item_{i}" for i in range(10000)]}

        async def large_result_task():
            yield TaskProgress(progress=100, message="Done", result=large_data)

        result = task_manager.submit(
            task_type=TaskType.ARCHIVE_CREATE,
            name="large_result",
            task_generator=large_result_task(),
        )

        task_result = await result.awaitable

        assert task_result.success is True
        assert task_result.data == large_data


class TestAwaitableSemantics:
    """Test awaitable semantics of submitted tasks."""

    async def test_awaitable_resolves_after_completion(self, task_manager):
        """Test that awaitable resolves only after task completion."""
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
        """Test that multiple awaits on the same future work correctly."""

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
