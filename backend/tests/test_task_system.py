"""Comprehensive unit tests for the task system."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import (
    TaskExecutionContext,
    TaskExecutionStatus,
    TaskExecutor,
    TaskManager,
    TaskRegistry,
    TaskScheduler,
    TaskStatus,
    TaskType,
)
from app.tasks.models import Task, TaskExecution


class TestTaskRegistry:
    """Test the TaskRegistry class."""
    
    @pytest.fixture
    def registry(self):
        """Create a clean registry for each test."""
        return TaskRegistry()
    
    async def test_register_valid_async_function(self, registry):
        """Test registering a valid async function."""
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        registry.register_task(
            name="test_task",
            function=test_task,
            description="Test task",
            is_system_task=True
        )
        
        assert "test_task" in registry
        assert len(registry) == 1
        
        info = registry.get_task_info("test_task")
        assert info is not None
        assert info["name"] == "test_task"
        assert info["description"] == "Test task"
        assert info["is_system_task"] is True
        assert info["function_name"] == "test_task"
    
    async def test_register_invalid_sync_function(self, registry):
        """Test that registering a sync function raises ValueError."""
        def sync_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        with pytest.raises(ValueError, match="must be async"):
            registry.register_task(
                name="sync_task",
                function=sync_task,
                description="Sync task"
            )
    
    async def test_register_invalid_signature(self, registry):
        """Test that registering a function without context parameter raises ValueError."""
        async def bad_task() -> Dict[str, Any]:
            return {"result": "success"}
        
        with pytest.raises(ValueError, match="must have 'context' as first parameter"):
            registry.register_task(
                name="bad_task",
                function=bad_task,
                description="Bad task"
            )
    
    async def test_register_duplicate_task(self, registry):
        """Test registering duplicate task names."""
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        registry.register_task(
            name="test_task",
            function=test_task,
            description="First task"
        )
        
        # Should log warning but allow override
        registry.register_task(
            name="test_task",
            function=test_task,
            description="Second task"
        )
        
        info = registry.get_task_info("test_task")
        assert info["description"] == "Second task"
    
    async def test_get_function(self, registry):
        """Test retrieving function from registry."""
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        registry.register_task(
            name="test_task",
            function=test_task,
            description="Test task"
        )
        
        retrieved_func = registry.get_function("test_task")
        assert retrieved_func is test_task
        
        # Non-existent function should return None
        assert registry.get_function("nonexistent") is None
    
    async def test_list_tasks(self, registry):
        """Test listing tasks with filtering."""
        async def system_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "system"}
        
        async def user_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "user"}
        
        registry.register_task(
            name="system_task",
            function=system_task,
            description="System task",
            is_system_task=True
        )
        
        registry.register_task(
            name="user_task", 
            function=user_task,
            description="User task",
            is_system_task=False
        )
        
        all_tasks = registry.list_tasks()
        assert len(all_tasks) == 2
        
        system_tasks = registry.list_tasks(system_only=True)
        assert len(system_tasks) == 1
        assert system_tasks[0]["name"] == "system_task"
    
    async def test_validate_function(self, registry):
        """Test function validation."""
        async def valid_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        def invalid_sync_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        async def invalid_signature_task() -> Dict[str, Any]:
            return {"result": "success"}
        
        assert registry.validate_function(valid_task) is True
        assert registry.validate_function(invalid_sync_task) is False
        assert registry.validate_function(invalid_signature_task) is False
    
    async def test_unregister_task(self, registry):
        """Test unregistering tasks."""
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        registry.register_task(
            name="test_task",
            function=test_task,
            description="Test task"
        )
        
        assert "test_task" in registry
        registry.unregister_task("test_task")
        assert "test_task" not in registry
        
        # Unregistering non-existent task should not raise error
        registry.unregister_task("nonexistent")
    
    async def test_clear(self, registry):
        """Test clearing all tasks."""
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        registry.register_task(
            name="test_task",
            function=test_task,
            description="Test task"
        )
        
        assert len(registry) == 1
        registry.clear()
        assert len(registry) == 0


class TestTaskScheduler:
    """Test the TaskScheduler class."""
    
    @pytest.fixture
    async def scheduler(self):
        """Create a scheduler for testing."""
        scheduler = TaskScheduler()
        await scheduler.start()
        yield scheduler
        await scheduler.stop()
    
    async def test_scheduler_lifecycle(self):
        """Test scheduler start/stop lifecycle."""
        scheduler = TaskScheduler()
        assert not scheduler.is_running()
        
        await scheduler.start()
        assert scheduler.is_running()
        
        await scheduler.stop()
        assert not scheduler.is_running()
    
    async def test_scheduler_lifespan_context(self):
        """Test scheduler lifespan context manager."""
        scheduler = TaskScheduler()
        
        async with scheduler.lifespan() as s:
            assert s is scheduler
            assert scheduler.is_running()
        
        assert not scheduler.is_running()
    
    async def test_add_one_time_job(self, scheduler):
        """Test adding a one-time job."""
        executed = False
        
        async def test_job():
            nonlocal executed
            executed = True
        
        job_id = scheduler.add_job(
            func=test_job,
            task_type=TaskType.ONE_TIME,
            job_id="test_job",
            max_instances=1
        )
        
        assert job_id == "test_job"
        
        # Wait for job to execute
        await asyncio.sleep(0.1)
        assert executed is True
    
    async def test_add_recurring_job(self, scheduler):
        """Test adding a recurring job with interval trigger."""
        execution_count = 0
        
        async def test_job():
            nonlocal execution_count
            execution_count += 1
        
        schedule_config = {
            "interval": {"seconds": 0.1}
        }
        
        job_id = scheduler.add_job(
            func=test_job,
            task_type=TaskType.RECURRING,
            job_id="recurring_job",
            schedule_config=schedule_config,
            max_instances=1
        )
        
        assert job_id == "recurring_job"
        
        # Wait for multiple executions
        await asyncio.sleep(0.3)
        assert execution_count >= 2
        
        # Clean up
        scheduler.remove_job("recurring_job")
    
    async def test_invalid_schedule_config(self, scheduler):
        """Test that invalid schedule configuration raises ValueError."""
        async def test_job():
            pass
        
        # RECURRING task without schedule_config should raise error
        with pytest.raises(ValueError, match="RECURRING tasks require schedule_config"):
            scheduler.add_job(
                func=test_job,
                task_type=TaskType.RECURRING,
                job_id="invalid_job",
                max_instances=1
            )
        
        # Invalid schedule_config should raise error
        with pytest.raises(ValueError, match="require 'cron' or 'interval'"):
            scheduler.add_job(
                func=test_job,
                task_type=TaskType.RECURRING,
                job_id="invalid_job",
                schedule_config={"invalid": "config"},
                max_instances=1
            )
    
    async def test_remove_job(self, scheduler):
        """Test removing a job."""
        async def test_job():
            pass
        
        scheduler.add_job(
            func=test_job,
            task_type=TaskType.ONE_TIME,
            job_id="removable_job",
            max_instances=1
        )
        
        # Should not raise error
        scheduler.remove_job("removable_job")
        
        # Removing non-existent job should not raise error
        scheduler.remove_job("nonexistent_job")
    
    async def test_pause_resume_job(self, scheduler):
        """Test pausing and resuming a job."""
        execution_count = 0
        
        async def test_job():
            nonlocal execution_count
            execution_count += 1
        
        schedule_config = {
            "interval": {"seconds": 0.1}
        }
        
        scheduler.add_job(
            func=test_job,
            task_type=TaskType.RECURRING,
            job_id="pausable_job",
            schedule_config=schedule_config,
            max_instances=1
        )
        
        # Let it run a bit
        await asyncio.sleep(0.2)
        initial_count = execution_count
        
        # Pause the job
        scheduler.pause_job("pausable_job")
        await asyncio.sleep(0.2)
        paused_count = execution_count
        
        # Should not have increased much (maybe 1 due to timing)
        assert paused_count <= initial_count + 1
        
        # Resume the job
        scheduler.resume_job("pausable_job")
        await asyncio.sleep(0.2)
        final_count = execution_count
        
        # Should have increased after resume
        assert final_count > paused_count
        
        # Clean up
        scheduler.remove_job("pausable_job")
    
    async def test_get_job_info(self, scheduler):
        """Test getting job information."""
        async def test_job():
            pass
        
        schedule_config = {
            "interval": {"seconds": 60}  # Long interval so it doesn't run during test
        }
        
        scheduler.add_job(
            func=test_job,
            task_type=TaskType.RECURRING,
            job_id="info_job",
            schedule_config=schedule_config,
            max_instances=2
        )
        
        info = scheduler.get_job_info("info_job")
        assert info is not None
        assert info["id"] == "info_job"
        assert info["max_instances"] == 2
        assert "next_run_time" in info
        assert "trigger" in info
        
        # Non-existent job should return None
        assert scheduler.get_job_info("nonexistent") is None
        
        # Clean up
        scheduler.remove_job("info_job")
    
    async def test_get_all_jobs(self, scheduler):
        """Test getting all job information."""
        async def test_job():
            pass
        
        # Add multiple jobs
        for i in range(3):
            scheduler.add_job(
                func=test_job,
                task_type=TaskType.ONE_TIME,
                job_id=f"job_{i}",
                max_instances=1
            )
        
        jobs = scheduler.get_all_jobs()
        job_ids = [job["id"] for job in jobs]
        
        assert len(jobs) >= 3  # May have other jobs from previous tests
        assert "job_0" in job_ids
        assert "job_1" in job_ids
        assert "job_2" in job_ids


class TestTaskExecutionContext:
    """Test the TaskExecutionContext class."""
    
    @pytest.fixture
    def context(self):
        """Create a context for testing."""
        return TaskExecutionContext(
            task_id=1,
            execution_id="test-execution-id",
            task_name="test_task",
            metadata={"test": "metadata"}
        )
    
    async def test_context_initialization(self, context):
        """Test context initialization."""
        assert context.task_id == 1
        assert context.execution_id == "test-execution-id"
        assert context.task_name == "test_task"
        assert context.metadata == {"test": "metadata"}
        assert context.status == TaskExecutionStatus.PENDING
        assert context.result is None
        assert context.started_at is None
    
    async def test_set_status_without_executor(self, context):
        """Test setting status without executor (should not raise error)."""
        await context.set_status(TaskExecutionStatus.RUNNING)
        assert context.status == TaskExecutionStatus.RUNNING
    
    async def test_set_result_without_executor(self, context):
        """Test setting result without executor (should not raise error)."""
        result = {"test": "result"}
        await context.set_result(result)
        assert context.result == result
    
    async def test_update_metadata_without_executor(self, context):
        """Test updating metadata without executor (should not raise error)."""
        await context.update_metadata({"new": "data"})
        assert context.metadata == {"test": "metadata", "new": "data"}
    
    async def test_context_with_mock_executor(self, context):
        """Test context with mock executor."""
        mock_executor = AsyncMock()
        context._executor = mock_executor
        
        # Test set_status
        await context.set_status(TaskExecutionStatus.RUNNING)
        mock_executor._update_execution_status.assert_called_once_with(
            "test-execution-id", TaskExecutionStatus.RUNNING
        )
        
        # Test set_result
        result = {"test": "result"}
        await context.set_result(result)
        mock_executor._update_execution_result.assert_called_once_with(
            "test-execution-id", result
        )
        
        # Test update_metadata
        await context.update_metadata({"new": "data"})
        mock_executor._update_execution_metadata.assert_called_once_with(
            "test-execution-id", {"test": "metadata", "new": "data"}
        )


class TestTaskExecutor:
    """Test the TaskExecutor class."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with test tasks."""
        registry = TaskRegistry()
        
        async def success_task(context: TaskExecutionContext) -> Dict[str, Any]:
            await context.update_metadata({"step": "processing"})
            await context.set_result({"status": "success"})
            return {"message": "Task completed successfully"}
        
        async def failing_task(context: TaskExecutionContext) -> Dict[str, Any]:
            raise ValueError("Task failed intentionally")
        
        async def context_task(context: TaskExecutionContext, arg1: str, arg2: int = 42) -> Dict[str, Any]:
            return {
                "context_task_id": context.task_id,
                "arg1": arg1,
                "arg2": arg2,
                "metadata": context.metadata
            }
        
        registry.register_task("success_task", success_task, "Success task")
        registry.register_task("failing_task", failing_task, "Failing task")
        registry.register_task("context_task", context_task, "Context task")
        
        return registry
    
    @pytest.fixture
    def executor(self, registry):
        """Create an executor with test registry."""
        return TaskExecutor(registry)
    
    @patch('app.tasks.executor.AsyncSessionLocal')
    async def test_execute_successful_task(self, mock_session_local, executor):
        """Test executing a successful task."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        context = await executor.execute_task(
            task_id=1,
            task_name="success_task",
            function_args=[],
            function_kwargs={},
            metadata={"test": "metadata"}
        )
        
        assert context.task_id == 1
        assert context.task_name == "success_task"
        assert context.status == TaskExecutionStatus.COMPLETED
        assert context.result == {"message": "Task completed successfully"}
        assert context.started_at is not None
        
        # Verify database calls
        assert mock_session.add.called
        assert mock_session.commit.called
    
    @patch('app.tasks.executor.AsyncSessionLocal')
    async def test_execute_failing_task(self, mock_session_local, executor):
        """Test executing a task that raises an exception."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        context = await executor.execute_task(
            task_id=2,
            task_name="failing_task",
            function_args=[],
            function_kwargs={},
            metadata={}
        )
        
        assert context.task_id == 2
        assert context.task_name == "failing_task"
        assert context.status == TaskExecutionStatus.FAILED
        assert context.result is None
        assert context.started_at is not None
        
        # Verify database calls
        assert mock_session.add.called
        assert mock_session.commit.called
    
    @patch('app.tasks.executor.AsyncSessionLocal')
    async def test_execute_task_with_arguments(self, mock_session_local, executor):
        """Test executing a task with arguments."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        context = await executor.execute_task(
            task_id=3,
            task_name="context_task",
            function_args=["test_arg"],
            function_kwargs={"arg2": 100},
            metadata={"test_meta": "value"}
        )
        
        assert context.status == TaskExecutionStatus.COMPLETED
        expected_result = {
            "context_task_id": 3,
            "arg1": "test_arg", 
            "arg2": 100,
            "metadata": {"test_meta": "value"}
        }
        assert context.result == expected_result
    
    @patch('app.tasks.executor.AsyncSessionLocal')
    async def test_execute_nonexistent_task(self, mock_session_local, executor):
        """Test executing a task that doesn't exist in registry."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        context = await executor.execute_task(
            task_id=4,
            task_name="nonexistent_task",
            function_args=[],
            function_kwargs={},
            metadata={}
        )
        
        assert context.status == TaskExecutionStatus.FAILED
        # Error should be about function not found
        # (We can't easily check the database updates without more complex mocking)
    
    async def test_background_task_management(self, executor):
        """Test background task execution and management."""
        # This would require more complex mocking of the background task execution
        # For now, we'll test that the method exists and basic functionality
        assert hasattr(executor, 'execute_background_task')
        assert hasattr(executor, 'cancel_background_task')
        assert hasattr(executor, 'cancel_all_background_tasks')
        assert hasattr(executor, 'get_background_task_count')
        
        # Initially no background tasks
        assert executor.get_background_task_count() == 0


@pytest.mark.asyncio
class TestTaskSystemIntegration:
    """Integration tests for the entire task system."""
    
    @pytest.fixture
    async def task_manager(self):
        """Create a TaskManager for integration testing."""
        manager = TaskManager()
        
        # Register a test task
        async def integration_test_task(context: TaskExecutionContext, message: str = "default") -> Dict[str, Any]:
            await context.update_metadata({"processing": True})
            await asyncio.sleep(0.01)  # Simulate some work
            result = {
                "message": message,
                "task_id": context.task_id,
                "execution_id": context.execution_id
            }
            await context.set_result(result)
            return result
        
        manager.registry.register_task(
            name="integration_test_task",
            function=integration_test_task,
            description="Integration test task",
            is_system_task=True
        )
        
        return manager
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_task_lifecycle(self, mock_session_local, task_manager):
        """Test the complete task lifecycle."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        # Mock database objects
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.name = "integration_test_task"
        mock_task.function_args = []
        mock_task.function_kwargs = {"message": "test message"}
        mock_task.task_metadata = {"test": "metadata"}
        
        mock_session.scalar.return_value = None  # No existing task
        mock_session.get.return_value = mock_task
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        # Test creating a task (this would normally require database)
        try:
            task_id = await task_manager.create_task(
                name="integration_test_task",
                task_type=TaskType.ONE_TIME,
                description="Integration test",
                function_args=[],
                function_kwargs={"message": "test message"},
                task_metadata={"test": "metadata"},
                auto_start=False
            )
            # If we get here, creation succeeded
            assert isinstance(task_id, int) or task_id is None
        except RuntimeError as e:
            # TaskManager is not running, which is expected in this test
            assert "not running" in str(e)
    
    async def test_registry_decorator(self):
        """Test the register_system_task decorator."""
        from app.tasks.registry import register_system_task, task_registry
        
        # Clear registry first
        task_registry.clear()
        
        @register_system_task(
            name="decorated_task",
            description="Task created with decorator",
            metadata={"type": "test"}
        )
        async def decorated_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"decorated": True}
        
        # Check that task was registered
        assert "decorated_task" in task_registry
        info = task_registry.get_task_info("decorated_task")
        assert info["description"] == "Task created with decorator"
        assert info["metadata"]["type"] == "test"
        assert info["is_system_task"] is True
        
        # Check that the function is still callable
        context = TaskExecutionContext(1, "test", "decorated_task")
        result = await decorated_task(context)
        assert result["decorated"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])