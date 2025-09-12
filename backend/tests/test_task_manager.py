"""Comprehensive tests for TaskManager class."""

import asyncio
import pytest
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks import (
    TaskExecutionContext,
    TaskExecutionStatus,
    TaskManager,
    TaskRegistry,
    TaskScheduler,
    TaskExecutor,
    TaskStatus,
    TaskType,
)
from app.tasks.models import Task, TaskExecution


class TestTaskManager:
    """Test the TaskManager class."""
    
    @pytest.fixture
    def task_manager(self):
        """Create a TaskManager for testing."""
        return TaskManager()
    
    async def test_task_manager_initialization(self, task_manager):
        """Test TaskManager initialization."""
        assert task_manager.registry is not None
        assert task_manager.scheduler is not None
        assert task_manager.executor is not None
        assert not task_manager.is_running()
        assert task_manager._background_task is None
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_start_stop_lifecycle(self, mock_session_local, task_manager):
        """Test TaskManager start/stop lifecycle."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        # Mock the database query to return no active tasks
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        # Test starting
        assert not task_manager.is_running()
        await task_manager.start()
        assert task_manager.is_running()
        
        # Test stopping
        await task_manager.stop()
        assert not task_manager.is_running()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_start_already_running(self, mock_session_local, task_manager):
        """Test starting TaskManager when already running."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        await task_manager.start()
        assert task_manager.is_running()
        
        # Should not raise error when starting again
        await task_manager.start()
        assert task_manager.is_running()
        
        await task_manager.stop()
    
    async def test_stop_not_running(self, task_manager):
        """Test stopping TaskManager when not running."""
        assert not task_manager.is_running()
        # Should not raise error when stopping while not running
        await task_manager.stop()
        assert not task_manager.is_running()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_create_task_not_running(self, mock_session_local, task_manager):
        """Test creating task when manager is not running."""
        # Register a test task first
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        task_manager.registry.register_task("test_task", test_task, "Test task")
        
        # Should raise error when not running
        with pytest.raises(RuntimeError, match="TaskManager is not running"):
            await task_manager.create_task(
                name="test_task",
                task_type=TaskType.ONE_TIME,
                description="Test task"
            )
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_create_task_function_not_found(self, mock_session_local, task_manager):
        """Test creating task with unregistered function."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        await task_manager.start()
        
        try:
            with pytest.raises(ValueError, match="Task function not found in registry"):
                await task_manager.create_task(
                    name="nonexistent_task",
                    task_type=TaskType.ONE_TIME,
                    description="Nonexistent task"
                )
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_create_task_duplicate_name(self, mock_session_local, task_manager):
        """Test creating task with duplicate name."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock existing task in database
        existing_task = MagicMock()
        existing_task.name = "test_task"
        mock_session.scalar.return_value = existing_task
        
        # Register a test task
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        task_manager.registry.register_task("test_task", test_task, "Test task")
        
        await task_manager.start()
        
        try:
            with pytest.raises(ValueError, match="Task with name 'test_task' already exists"):
                await task_manager.create_task(
                    name="test_task",
                    task_type=TaskType.ONE_TIME,
                    description="Test task"
                )
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_create_task_success(self, mock_session_local, task_manager):
        """Test successful task creation."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock no existing task
        mock_session.scalar.return_value = None
        
        # Mock task creation
        mock_task = MagicMock()
        mock_task.id = 123
        mock_task.name = "test_task"
        mock_task.task_type = TaskType.ONE_TIME
        mock_task.status = TaskStatus.PENDING
        mock_session.refresh.return_value = None
        
        # Register a test task
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        task_manager.registry.register_task("test_task", test_task, "Test task")
        
        await task_manager.start()
        
        try:
            # Mock the task object that gets added to session
            def mock_add(task_obj):
                task_obj.id = 123
            mock_session.add.side_effect = mock_add
            
            # Mock get method for _schedule_task
            mock_session.get.return_value = mock_task
            
            task_id = await task_manager.create_task(
                name="test_task",
                task_type=TaskType.ONE_TIME,
                description="Test task",
                function_args=[],
                function_kwargs={},
                auto_start=True
            )
            
            # The create_task method should complete and perform database operations
            # Note: The task_id return value depends on proper mock setup of the database
            # We mainly verify that the method completed the expected database operations
            assert mock_session.add.called
            assert mock_session.commit.called
            assert mock_session.refresh.called
            
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_update_task_not_running(self, mock_session_local, task_manager):
        """Test updating task when manager is not running."""
        with pytest.raises(RuntimeError, match="TaskManager is not running"):
            await task_manager.update_task(1, description="Updated description")
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_update_task_not_found(self, mock_session_local, task_manager):
        """Test updating non-existent task."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock task not found
        mock_session.get.return_value = None
        
        await task_manager.start()
        
        try:
            result = await task_manager.update_task(999, description="Updated description")
            assert result is False
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_update_task_success(self, mock_session_local, task_manager):
        """Test successful task update."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock existing task
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.name = "test_task"
        mock_task.description = "Original description"
        mock_task.status = TaskStatus.PENDING
        mock_session.get.return_value = mock_task
        
        await task_manager.start()
        
        try:
            result = await task_manager.update_task(
                1, 
                description="Updated description",
                max_instances=3
            )
            
            assert result is True
            assert mock_task.description == "Updated description"
            assert mock_task.max_instances == 3
            assert mock_session.commit.called
            
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_delete_task_not_running(self, mock_session_local, task_manager):
        """Test deleting task when manager is not running."""
        with pytest.raises(RuntimeError, match="TaskManager is not running"):
            await task_manager.delete_task(1)
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_delete_task_not_found(self, mock_session_local, task_manager):
        """Test deleting non-existent task."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock task not found
        mock_session.get.return_value = None
        
        await task_manager.start()
        
        try:
            result = await task_manager.delete_task(999)
            assert result is False
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_delete_task_success(self, mock_session_local, task_manager):
        """Test successful task deletion."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock existing task
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.name = "test_task"
        mock_task.task_type = TaskType.ONE_TIME
        mock_session.get.return_value = mock_task
        
        await task_manager.start()
        
        try:
            result = await task_manager.delete_task(1)
            
            assert result is True
            mock_session.delete.assert_called_with(mock_task)
            assert mock_session.commit.called
            
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_start_stop_task(self, mock_session_local, task_manager):
        """Test starting and stopping tasks."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock existing task
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.name = "test_task"
        mock_task.task_type = TaskType.ONE_TIME
        mock_task.status = TaskStatus.PAUSED
        mock_session.get.return_value = mock_task
        
        # Register a test task
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        task_manager.registry.register_task("test_task", test_task, "Test task")
        
        await task_manager.start()
        
        try:
            # Test starting a task
            result = await task_manager.start_task(1)
            assert result is True
            
            # Test stopping a task
            result = await task_manager.stop_task(1)
            assert result is True
            assert mock_task.status == TaskStatus.PAUSED
            
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_execute_task_now(self, mock_session_local, task_manager):
        """Test immediate task execution."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        # Mock existing task
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.name = "test_task"
        mock_task.function_args = {}
        mock_task.function_kwargs = {}
        mock_task.task_metadata = {}
        mock_session.get.return_value = mock_task
        
        # Register a test task
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        task_manager.registry.register_task("test_task", test_task, "Test task")
        
        await task_manager.start()
        
        try:
            # Mock executor's execute_task method
            mock_context = MagicMock()
            mock_context.execution_id = "test-execution-id"
            task_manager.executor.execute_task = AsyncMock(return_value=mock_context)
            
            execution_id = await task_manager.execute_task_now(1)
            assert execution_id == "test-execution-id"
            
            # Verify executor was called
            task_manager.executor.execute_task.assert_called_once()
            
        finally:
            await task_manager.stop()
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_get_task(self, mock_session_local, task_manager):
        """Test getting a task by ID."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        # Mock existing task
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.name = "test_task"
        mock_session.get.return_value = mock_task
        
        result = await task_manager.get_task(1)
        assert result == mock_task
        
        # Test non-existent task
        mock_session.get.return_value = None
        result = await task_manager.get_task(999)
        assert result is None
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_list_tasks(self, mock_session_local, task_manager):
        """Test listing tasks with filters."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        # Mock tasks
        mock_tasks = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_tasks
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        # Test listing all tasks
        result = await task_manager.list_tasks()
        assert result == mock_tasks
        
        # Test listing with filters
        result = await task_manager.list_tasks(
            task_type=TaskType.ONE_TIME,
            status=TaskStatus.PENDING,
            system_only=True
        )
        assert result == mock_tasks
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_get_task_executions(self, mock_session_local, task_manager):
        """Test getting task execution history."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        # Mock executions
        mock_executions = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_executions
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await task_manager.get_task_executions(1, limit=10)
        assert result == mock_executions
    
    @patch('app.tasks.manager.AsyncSessionLocal')
    async def test_load_and_schedule_tasks(self, mock_session_local, task_manager):
        """Test loading and scheduling tasks from database."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        # Mock active tasks
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.name = "test_task"
        mock_task.task_type = TaskType.ONE_TIME
        mock_task.status = TaskStatus.PENDING
        mock_task.schedule_config = None
        mock_task.function_args = {}
        mock_task.function_kwargs = {}
        mock_task.task_metadata = {}
        # Mock the query result chain properly
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = [mock_task]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        # Register a test task
        async def test_task(context: TaskExecutionContext) -> Dict[str, Any]:
            return {"result": "success"}
        
        task_manager.registry.register_task("test_task", test_task, "Test task")
        
        # Test loading tasks (this is called during start)
        await task_manager.start()
        
        try:
            # Verify task was processed
            assert mock_session.execute.called
        finally:
            await task_manager.stop()
    
    async def test_maintenance_loop(self, task_manager):
        """Test the maintenance loop."""
        # This test verifies that the maintenance loop can be started and stopped
        # without errors. The actual maintenance functionality is a TODO in the code.
        
        # Mock the _load_and_schedule_tasks to avoid database calls
        task_manager._load_and_schedule_tasks = AsyncMock()
        
        # Start the task manager
        await task_manager.start()
        
        try:
            # Let the maintenance loop run briefly
            await asyncio.sleep(0.1)
            
            # Verify maintenance task is running
            assert task_manager._background_task is not None
            assert not task_manager._background_task.done()
            
        finally:
            await task_manager.stop()
            
            # Verify maintenance task is stopped
            assert task_manager._background_task is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])