"""Task execution engine for managing task lifecycle and execution."""

import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from ..db.database import AsyncSessionLocal
from .models import TaskExecution, TaskExecutionStatus
from .registry import TaskRegistry

logger = logging.getLogger(__name__)


class TaskExecutionContext:
    """Context object passed to tasks during execution."""
    
    def __init__(
        self,
        task_id: int,
        execution_id: str,
        task_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.task_id = task_id
        self.execution_id = execution_id
        self.task_name = task_name
        self.metadata = metadata or {}
        self.status = TaskExecutionStatus.PENDING
        self.started_at: Optional[datetime] = None
        self.result: Optional[Dict[str, Any]] = None
        self._executor: Optional["TaskExecutor"] = None
    
    async def set_status(self, status: TaskExecutionStatus) -> None:
        """Update the execution status."""
        self.status = status
        if self._executor:
            await self._executor._update_execution_status(
                self.execution_id, status
            )
    
    async def set_result(self, result: Dict[str, Any]) -> None:
        """Set the execution result."""
        self.result = result
        if self._executor:
            await self._executor._update_execution_result(
                self.execution_id, result
            )
    
    async def update_metadata(self, metadata: Dict[str, Any]) -> None:
        """Update execution metadata."""
        self.metadata.update(metadata)
        if self._executor:
            await self._executor._update_execution_metadata(
                self.execution_id, self.metadata
            )


class TaskExecutor:
    """Executes tasks and manages their execution lifecycle."""
    
    def __init__(self, registry: TaskRegistry):
        self.registry = registry
        self._background_tasks: Dict[str, asyncio.Task] = {}
    
    async def execute_task(
        self,
        task_id: int,
        task_name: str,
        function_args: Optional[Dict[str, Any]] = None,
        function_kwargs: Optional[Dict[str, Any]] = None,
        apscheduler_job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionContext:
        """Execute a task and manage its lifecycle.
        
        Args:
            task_id: Database task ID
            task_name: Task name for logging
            function_args: Arguments to pass to the function (after context)
            function_kwargs: Keyword arguments to pass to the function
            apscheduler_job_id: APScheduler job ID if applicable
            metadata: Additional execution metadata
            
        Returns:
            Task execution context
        """
        execution_id = str(uuid.uuid4())
        context = TaskExecutionContext(
            task_id=task_id,
            execution_id=execution_id,
            task_name=task_name,
            metadata=metadata
        )
        context._executor = self
        
        # Create execution record
        async with AsyncSessionLocal() as session:
            execution = TaskExecution(
                task_id=task_id,
                execution_id=execution_id,
                apscheduler_job_id=apscheduler_job_id,
                status=TaskExecutionStatus.PENDING,
                execution_metadata=metadata or {}
            )
            session.add(execution)
            await session.commit()
        
        logger.info(f"Starting task execution: {task_name} (ID: {execution_id})")
        
        try:
            # Get the function from registry
            function = self.registry.get_function(task_name)
            if not function:
                raise ValueError(f"Task function not found in registry: {task_name}")
            
            # Set context and update status
            await context.set_status(TaskExecutionStatus.RUNNING)
            context.started_at = datetime.now(timezone.utc)
            
            # Update execution record
            await self._update_execution_started(execution_id, context.started_at)
            
            # Execute the function with context as first parameter
            args = [context] + list(function_args or [])
            kwargs = function_kwargs or {}
            
            result = await function(*args, **kwargs)
            
            # Handle result
            if result is not None:
                if isinstance(result, dict):
                    await context.set_result(result)
                else:
                    await context.set_result({"return_value": result})
            
            await context.set_status(TaskExecutionStatus.COMPLETED)
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - context.started_at).total_seconds()
            
            await self._update_execution_completed(
                execution_id, completed_at, duration, context.result
            )
            
            logger.info(
                f"Task execution completed: {task_name} (ID: {execution_id}, "
                f"Duration: {duration:.2f}s)"
            )
            
        except Exception as e:
            error_message = str(e)
            error_traceback = traceback.format_exc()
            
            await context.set_status(TaskExecutionStatus.FAILED)
            completed_at = datetime.now(timezone.utc)
            duration = None
            if context.started_at:
                duration = (completed_at - context.started_at).total_seconds()
            
            await self._update_execution_failed(
                execution_id, completed_at, duration, error_message, error_traceback
            )
            
            logger.error(
                f"Task execution failed: {task_name} (ID: {execution_id}): {error_message}"
            )
            logger.debug(f"Task failure traceback:\n{error_traceback}")
            
        finally:
            # Context cleanup is automatic since we're not using globals
            pass
        
        return context
    
    async def execute_background_task(
        self,
        task_id: int,
        task_name: str,
        function_args: Optional[Dict[str, Any]] = None,
        function_kwargs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Execute a background task that runs continuously.
        
        Args:
            task_id: Database task ID
            task_name: Task name for logging
            function_args: Arguments to pass to the function (after context)
            function_kwargs: Keyword arguments to pass to the function
            metadata: Additional execution metadata
            
        Returns:
            Background task key for management
        """
        task_key = f"bg_{task_id}_{uuid.uuid4().hex[:8]}"
        
        async def background_wrapper():
            """Wrapper that handles background task lifecycle."""
            while True:
                try:
                    context = await self.execute_task(
                        task_id=task_id,
                        task_name=task_name,
                        function_args=function_args,
                        function_kwargs=function_kwargs,
                        metadata=metadata
                    )
                    
                    # If the task completed successfully, it might want to schedule next run
                    # For now, we'll just wait a bit and run again
                    # TODO: Make this configurable or let the task control its own schedule
                    await asyncio.sleep(60)  # Wait 1 minute between runs
                    
                except asyncio.CancelledError:
                    logger.info(f"Background task cancelled: {task_name}")
                    break
                except Exception as e:
                    logger.error(f"Background task error: {task_name}: {e}")
                    await asyncio.sleep(60)  # Wait before retry
        
        task = asyncio.create_task(background_wrapper())
        self._background_tasks[task_key] = task
        
        logger.info(f"Started background task: {task_name} (Key: {task_key})")
        return task_key
    
    async def cancel_background_task(self, task_key: str) -> bool:
        """Cancel a background task.
        
        Args:
            task_key: Background task key returned by execute_background_task
            
        Returns:
            True if task was cancelled, False if not found
        """
        if task_key in self._background_tasks:
            task = self._background_tasks[task_key]
            task.cancel()
            del self._background_tasks[task_key]
            logger.info(f"Cancelled background task: {task_key}")
            return True
        return False
    
    async def cancel_all_background_tasks(self) -> None:
        """Cancel all background tasks."""
        for task_key in list(self._background_tasks.keys()):
            await self.cancel_background_task(task_key)
    
    def get_background_task_count(self) -> int:
        """Get the number of running background tasks."""
        return len(self._background_tasks)
    
    async def _update_execution_status(
        self, execution_id: str, status: TaskExecutionStatus
    ) -> None:
        """Update execution status in database."""
        try:
            async with AsyncSessionLocal() as session:
                result_obj = await session.execute(
                    select(TaskExecution).where(TaskExecution.execution_id == execution_id)
                )
                execution = result_obj.scalar_one_or_none()
                if execution:
                    execution.status = status
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to update execution status: {e}")
    
    async def _update_execution_started(
        self, execution_id: str, started_at: datetime
    ) -> None:
        """Update execution started timestamp."""
        try:
            async with AsyncSessionLocal() as session:
                result_obj = await session.execute(
                    select(TaskExecution).where(TaskExecution.execution_id == execution_id)
                )
                execution = result_obj.scalar_one_or_none()
                if execution:
                    execution.status = TaskExecutionStatus.RUNNING
                    execution.started_at = started_at
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to update execution start time: {e}")
    
    async def _update_execution_completed(
        self,
        execution_id: str,
        completed_at: datetime,
        duration: float,
        result: Optional[Dict[str, Any]]
    ) -> None:
        """Update execution completion."""
        try:
            async with AsyncSessionLocal() as session:
                # Note: In a real implementation, you'd use proper SQLAlchemy update
                # This is a simplified version for the example
                result_obj = await session.execute(
                    select(TaskExecution).where(TaskExecution.execution_id == execution_id)
                )
                execution = result_obj.scalar_one_or_none()
                if execution:
                    execution.status = TaskExecutionStatus.COMPLETED
                    execution.completed_at = completed_at
                    execution.duration_seconds = duration
                    if result:
                        execution.result = result
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to update execution completion: {e}")
    
    async def _update_execution_failed(
        self,
        execution_id: str,
        completed_at: datetime,
        duration: Optional[float],
        error_message: str,
        error_traceback: str
    ) -> None:
        """Update execution failure."""
        try:
            async with AsyncSessionLocal() as session:
                result_obj = await session.execute(
                    select(TaskExecution).where(TaskExecution.execution_id == execution_id)
                )
                execution = result_obj.scalar_one_or_none()
                if execution:
                    execution.status = TaskExecutionStatus.FAILED
                    execution.completed_at = completed_at
                    if duration:
                        execution.duration_seconds = duration
                    execution.error_message = error_message
                    execution.error_traceback = error_traceback
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to update execution failure: {e}")
    
    async def _update_execution_result(
        self, execution_id: str, result: Dict[str, Any]
    ) -> None:
        """Update execution result."""
        try:
            async with AsyncSessionLocal() as session:
                result_obj = await session.execute(
                    select(TaskExecution).where(TaskExecution.execution_id == execution_id)
                )
                execution = result_obj.scalar_one_or_none()
                if execution:
                    execution.result = result
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to update execution result: {e}")
    
    async def _update_execution_metadata(
        self, execution_id: str, metadata: Dict[str, Any]
    ) -> None:
        """Update execution metadata."""
        try:
            async with AsyncSessionLocal() as session:
                result_obj = await session.execute(
                    select(TaskExecution).where(TaskExecution.execution_id == execution_id)
                )
                execution = result_obj.scalar_one_or_none()
                if execution:
                    execution.execution_metadata = metadata
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to update execution metadata: {e}")