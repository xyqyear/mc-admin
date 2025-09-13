"""Tests for the simplified task system."""

import asyncio
from datetime import datetime
from functools import partial
from typing import Any, Dict

import pytest

from app.tasks import TaskInfo, TaskManager, TaskStatus, TaskType


class TestTaskManager:
    """Test the TaskManager functionality."""

    @pytest.fixture
    async def manager(self):
        """Create a task manager for testing."""
        manager = TaskManager()
        await manager.start()
        yield manager

    async def test_manager_lifecycle(self):
        """Test starting the task manager."""
        manager = TaskManager()
        assert not manager.is_running()

        await manager.start()
        assert manager.is_running()

    async def test_submit_simple_task(self, manager):
        """Test submitting a simple task."""

        async def hello_task():
            return "Hello, World!"

        task_info = manager.submit_task(hello_task, "hello")

        # Verify task info
        assert task_info.task_name == "hello"
        assert task_info.status == TaskStatus.RUNNING
        assert task_info.task_id is not None
        assert isinstance(task_info.created_at, datetime)

        # Wait for completion
        await asyncio.sleep(0.1)

        # Check final status
        updated_info = manager.get_task(task_info.task_id)
        assert updated_info is not None
        assert updated_info.status == TaskStatus.COMPLETED
        assert updated_info.result == "Hello, World!"
        assert updated_info.completed_at is not None

    async def test_submit_task_with_parameters(self, manager):
        """Test submitting a task with parameters using partial."""

        async def process_data(data_id: str, multiplier: int) -> Dict[str, Any]:
            return {"data_id": data_id, "result": multiplier * 2}

        # Use partial to bind parameters
        task_func = partial(process_data, "test123", 5)
        task_info = manager.submit_task(
            task_func,
            "data_processing",
            description="Process data with multiplier",
            metadata={"data_id": "test123", "multiplier": 5},
        )

        # Verify task info with new fields
        assert task_info.description == "Process data with multiplier"
        assert task_info.metadata == {"data_id": "test123", "multiplier": 5}

        # Wait for completion
        await asyncio.sleep(0.1)

        # Check result
        updated_info = manager.get_task(task_info.task_id)
        assert updated_info is not None
        assert updated_info.status == TaskStatus.COMPLETED
        assert updated_info.result == {"data_id": "test123", "result": 10}
        assert updated_info.execution_count == 1
        assert updated_info.last_run_at is not None

    async def test_submit_failing_task(self, manager):
        """Test submitting a task that fails."""

        async def failing_task():
            raise ValueError("Test error")

        task_info = manager.submit_task(failing_task, "failing")

        # Wait for failure
        await asyncio.sleep(0.1)

        # Check error status
        updated_info = manager.get_task(task_info.task_id)
        assert updated_info is not None
        assert updated_info.status == TaskStatus.FAILED
        assert updated_info.error_message == "Test error"
        assert updated_info.completed_at is not None

    async def test_cancel_task(self, manager):
        """Test cancelling a running task."""

        async def long_task():
            await asyncio.sleep(10)  # Long running task
            return "completed"

        task_info = manager.submit_task(long_task, "long_task")

        # Cancel immediately
        success = manager.cancel_task(task_info.task_id)
        assert success is True

        # Wait a bit
        await asyncio.sleep(0.1)

        # Check cancellation status
        updated_info = manager.get_task(task_info.task_id)
        assert updated_info is not None
        assert updated_info.status == TaskStatus.CANCELLED

    async def test_get_task_not_found(self, manager):
        """Test getting a task that doesn't exist."""
        result = manager.get_task("nonexistent")
        assert result is None

    async def test_get_all_tasks(self, manager):
        """Test getting all tasks."""
        # Initially empty
        tasks = manager.get_all_tasks()
        assert len(tasks) == 0

        # Submit some tasks with different types
        async def simple_task(name: str):
            return f"Task {name}"

        task1_func = partial(simple_task, "1")
        task2_func = partial(simple_task, "2")

        info1 = manager.submit_task(task1_func, "task1")  # oneshot task
        info2 = manager.schedule_task(
            task2_func, "task2", interval_seconds=1
        )  # scheduled task

        # Check all tasks
        all_tasks = manager.get_all_tasks()
        assert len(all_tasks) == 2

        task_ids = {task.task_id for task in all_tasks}
        assert info1.task_id in task_ids
        assert info2.task_id in task_ids

        # Test task type filtering
        oneshot_tasks = manager.get_oneshot_tasks()
        assert len(oneshot_tasks) == 1
        assert oneshot_tasks[0].task_id == info1.task_id
        assert oneshot_tasks[0].task_type == TaskType.ONESHOT

        scheduled_tasks = manager.get_scheduled_tasks()
        assert len(scheduled_tasks) == 1
        assert scheduled_tasks[0].task_id == info2.task_id
        assert scheduled_tasks[0].task_type == TaskType.SCHEDULED

        # Clean up scheduled task
        manager.cancel_task(info2.task_id)

    async def test_schedule_task_interval(self, manager):
        """Test scheduling a task with interval."""
        execution_count = 0

        async def periodic_task():
            nonlocal execution_count
            execution_count += 1
            return f"Execution {execution_count}"

        # Schedule to run every 0.1 seconds with metadata
        task_info = manager.schedule_task(
            periodic_task,
            "periodic",
            interval_seconds=0.1,
            description="Periodic test task",
            metadata={"period": 0.1, "type": "test"},
        )

        assert task_info.task_name == "periodic"
        assert task_info.status == TaskStatus.RUNNING
        assert task_info.description == "Periodic test task"
        assert task_info.metadata == {"period": 0.1, "type": "test"}
        assert task_info.interval_seconds == 0.1
        assert task_info.task_type == TaskType.SCHEDULED

        # Let it run a few times
        await asyncio.sleep(0.35)

        # Should have executed multiple times
        assert execution_count >= 2

        # Check execution count was tracked
        updated_info = manager.get_task(task_info.task_id)
        assert updated_info is not None
        assert updated_info.execution_count >= 2
        assert updated_info.last_run_at is not None

        # Cancel the scheduled task
        success = manager.cancel_task(task_info.task_id)
        assert success is True

    async def test_schedule_task_cron(self, manager):
        """Test scheduling a task with cron expression."""

        async def cron_task():
            return "Cron task executed"

        # Test that cron scheduling works (we won't wait for actual execution)
        task_info = manager.schedule_task(
            cron_task,
            "cron_task",
            cron_expression="0 2 * * *",  # Every day at 2 AM
        )

        # Verify task was scheduled
        assert task_info.task_name == "cron_task"
        assert task_info.status == TaskStatus.RUNNING

        # Cancel the task immediately since we don't want to wait for 2 AM
        success = manager.cancel_task(task_info.task_id)
        assert success is True

    async def test_schedule_task_no_trigger(self, manager):
        """Test scheduling a task without trigger raises error."""

        async def dummy_task():
            pass

        with pytest.raises(
            ValueError,
            match="Either cron_expression or interval_seconds must be provided",
        ):
            manager.schedule_task(dummy_task, "no_trigger")

    async def test_manager_not_running_errors(self):
        """Test operations on non-running manager raise errors."""
        manager = TaskManager()

        async def dummy_task():
            pass

        with pytest.raises(RuntimeError, match="TaskManager is not running"):
            manager.submit_task(dummy_task, "test")

        with pytest.raises(RuntimeError, match="TaskManager is not running"):
            manager.schedule_task(dummy_task, "test", interval_seconds=1)

    async def test_background_task_simulation(self, manager):
        """Test a background task that runs continuously."""
        iteration_count = 0
        max_iterations = 3

        async def background_monitor():
            nonlocal iteration_count
            while iteration_count < max_iterations:
                iteration_count += 1
                await asyncio.sleep(0.1)
            return f"Completed {iteration_count} iterations"

        task_info = manager.submit_task(background_monitor, "monitor")

        # Let it run
        await asyncio.sleep(0.5)

        # Check completion
        updated_info = manager.get_task(task_info.task_id)
        assert updated_info is not None
        assert updated_info.status == TaskStatus.COMPLETED
        assert iteration_count == max_iterations

    async def test_get_task_schedule_info(self, manager):
        """Test getting detailed schedule information for tasks."""

        # Create a scheduled task
        async def test_task():
            return "test result"

        task_info = manager.schedule_task(
            test_task,
            "test_scheduled",
            interval_seconds=5,
            description="Test scheduled task",
            metadata={"test": "value"},
        )

        # Get schedule info
        schedule_info = manager.get_task_schedule_info(task_info.task_id)
        assert schedule_info is not None
        assert schedule_info["task_id"] == task_info.task_id
        assert schedule_info["task_name"] == "test_scheduled"
        assert schedule_info["task_type"] == TaskType.SCHEDULED
        assert schedule_info["interval_seconds"] == 5
        assert schedule_info["cron_expression"] is None
        assert schedule_info["execution_count"] == 0
        assert schedule_info["last_run_at"] is None
        assert schedule_info["next_run_at"] is not None
        assert schedule_info["start_time"] is None

        # Test with non-existent task
        no_schedule_info = manager.get_task_schedule_info("nonexistent")
        assert no_schedule_info is None

        # Clean up
        manager.cancel_task(task_info.task_id)


class TestTaskInfo:
    """Test TaskInfo dataclass."""

    def test_task_info_creation(self):
        """Test creating TaskInfo instance."""
        now = datetime.now()
        task_info = TaskInfo(
            task_id="test-123",
            task_name="test_task",
            status=TaskStatus.RUNNING,
            task_type=TaskType.ONESHOT,
            created_at=now,
            description="Test task description",
            metadata={"key": "value", "number": 42},
        )

        assert task_info.task_id == "test-123"
        assert task_info.task_name == "test_task"
        assert task_info.status == TaskStatus.RUNNING
        assert task_info.task_type == TaskType.ONESHOT
        assert task_info.created_at == now
        assert task_info.description == "Test task description"
        assert task_info.metadata == {"key": "value", "number": 42}
        assert task_info.completed_at is None
        assert task_info.error_message is None
        assert task_info.result is None
        assert task_info.execution_count == 0
        assert task_info.last_run_at is None
        assert task_info.cron_expression is None
        assert task_info.interval_seconds is None
        assert task_info.next_run_at is None
        assert task_info.start_time is None

    def test_task_status_enum(self):
        """Test TaskStatus enum values."""
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_task_type_enum(self):
        """Test TaskType enum values."""
        assert TaskType.ONESHOT == "oneshot"
        assert TaskType.SCHEDULED == "scheduled"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
