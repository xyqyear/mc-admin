"""Task management system for MC Admin."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from ..db.database import AsyncSessionLocal
from .executor import TaskExecutor
from .models import Task, TaskExecution, TaskStatus, TaskType
from .registry import TaskRegistry
from .scheduler import TaskScheduler

logger = logging.getLogger(__name__)


class TaskManager:
    """Main task management class that coordinates scheduling and execution."""
    
    def __init__(self):
        self.registry = TaskRegistry()
        self.scheduler = TaskScheduler()
        self.executor = TaskExecutor(self.registry)
        self._running = False
        self._background_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the task management system."""
        if self._running:
            logger.warning("TaskManager is already running")
            return
        
        logger.info("Starting TaskManager")
        
        try:
            # Start the scheduler
            await self.scheduler.start()
            
            # Load and schedule existing tasks from database
            await self._load_and_schedule_tasks()
            
            # Start background maintenance task
            self._background_task = asyncio.create_task(self._maintenance_loop())
            
            self._running = True
            logger.info("TaskManager started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start TaskManager: {e}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the task management system."""
        if not self._running:
            logger.warning("TaskManager is not running")
            return
        
        logger.info("Stopping TaskManager")
        
        try:
            # Stop background maintenance
            if self._background_task:
                self._background_task.cancel()
                try:
                    await self._background_task
                except asyncio.CancelledError:
                    pass
                self._background_task = None
            
            # Stop all background tasks
            await self.executor.cancel_all_background_tasks()
            
            # Stop scheduler
            await self.scheduler.stop()
            
            self._running = False
            logger.info("TaskManager stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping TaskManager: {e}")
            raise
    
    def is_running(self) -> bool:
        """Check if the task manager is running."""
        return self._running
    
    async def create_task(
        self,
        name: str,
        task_type: TaskType,
        description: Optional[str] = None,
        function_args: Optional[Dict[str, Any]] = None,
        function_kwargs: Optional[Dict[str, Any]] = None,
        schedule_config: Optional[Dict[str, Any]] = None,
        max_instances: int = 1,
        misfire_grace_time: Optional[int] = None,
        jitter: Optional[int] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
        is_system_task: bool = False,
        created_by_user_id: Optional[int] = None,
        auto_start: bool = True
    ) -> int:
        """Create a new task.
        
        Args:
            name: Unique task name
            task_type: Type of task (ONE_TIME, RECURRING, BACKGROUND)
            description: Task description
            function_args: Arguments to pass to the function (after context)
            function_kwargs: Keyword arguments to pass to the function
            schedule_config: Scheduling configuration for APScheduler
            max_instances: Maximum concurrent instances
            misfire_grace_time: Grace time for misfired jobs in seconds
            jitter: Random delay in seconds
            task_metadata: Additional metadata
            is_system_task: Whether this is a system task
            created_by_user_id: User ID who created the task (if applicable)
            auto_start: Whether to automatically start the task
            
        Returns:
            Task ID
            
        Raises:
            ValueError: If task configuration is invalid
            RuntimeError: If task manager is not running
        """
        if not self._running:
            raise RuntimeError("TaskManager is not running")
        
        # Validate function exists in registry
        if name not in self.registry:
            raise ValueError(f"Task function not found in registry: {name}")
        
        async with AsyncSessionLocal() as session:
            # Check for duplicate task name
            existing = await session.scalar(
                select(Task).where(Task.name == name)
            )
            if existing:
                raise ValueError(f"Task with name '{name}' already exists")
            
            # Create task in database
            task = Task(
                name=name,
                description=description,
                task_type=task_type,
                function_args=function_args or {},
                function_kwargs=function_kwargs or {},
                schedule_config=schedule_config,
                max_instances=max_instances,
                misfire_grace_time=misfire_grace_time,
                jitter=jitter,
                task_metadata=task_metadata or {},
                is_system_task=is_system_task,
                created_by_user_id=created_by_user_id,
                status=TaskStatus.PENDING
            )
            
            session.add(task)
            await session.commit()
            await session.refresh(task)
            
            task_id = task.id
            logger.info(f"Created task: {name} (ID: {task_id})")
            
            # Schedule the task if auto_start is True
            if auto_start:
                await self._schedule_task(task)
            
            return task_id
    
    async def update_task(
        self,
        task_id: int,
        **updates
    ) -> bool:
        """Update an existing task.
        
        Args:
            task_id: Task ID to update
            **updates: Fields to update
            
        Returns:
            True if task was updated, False if not found
        """
        if not self._running:
            raise RuntimeError("TaskManager is not running")
        
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return False
            
            # Update allowed fields
            allowed_fields = {
                'description', 'status', 'schedule_config', 'max_instances',
                'misfire_grace_time', 'jitter', 'task_metadata'
            }
            
            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(task, field, value)
            
            task.updated_at = datetime.now(timezone.utc)
            await session.commit()
            
            logger.info(f"Updated task: {task.name} (ID: {task_id})")
            
            # Re-schedule if necessary
            if 'schedule_config' in updates or 'status' in updates:
                await self._reschedule_task(task)
            
            return True
    
    async def delete_task(self, task_id: int) -> bool:
        """Delete a task.
        
        Args:
            task_id: Task ID to delete
            
        Returns:
            True if task was deleted, False if not found
        """
        if not self._running:
            raise RuntimeError("TaskManager is not running")
        
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return False
            
            # Stop the task first
            await self._unschedule_task(task)
            
            # Delete from database
            await session.delete(task)
            await session.commit()
            
            logger.info(f"Deleted task: {task.name} (ID: {task_id})")
            return True
    
    async def start_task(self, task_id: int) -> bool:
        """Start/resume a task.
        
        Args:
            task_id: Task ID to start
            
        Returns:
            True if task was started, False if not found
        """
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return False
            
            if task.status != TaskStatus.PAUSED:
                task.status = TaskStatus.PENDING
                await session.commit()
            
            await self._schedule_task(task)
            logger.info(f"Started task: {task.name} (ID: {task_id})")
            return True
    
    async def stop_task(self, task_id: int) -> bool:
        """Stop/pause a task.
        
        Args:
            task_id: Task ID to stop
            
        Returns:
            True if task was stopped, False if not found
        """
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return False
            
            task.status = TaskStatus.PAUSED
            await session.commit()
            
            await self._unschedule_task(task)
            logger.info(f"Stopped task: {task.name} (ID: {task_id})")
            return True
    
    async def execute_task_now(self, task_id: int) -> Optional[str]:
        """Execute a task immediately.
        
        Args:
            task_id: Task ID to execute
            
        Returns:
            Execution ID if successful, None if task not found
        """
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return None
            
            # Execute the task directly
            context = await self.executor.execute_task(
                task_id=task.id,
                task_name=task.name,
                function_args=task.function_args,
                function_kwargs=task.function_kwargs,
                metadata=task.task_metadata
            )
            
            # Update last run time
            task.last_run_at = datetime.now(timezone.utc)
            await session.commit()
            
            return context.execution_id
    
    async def get_task(self, task_id: int) -> Optional[Task]:
        """Get a task by ID."""
        async with AsyncSessionLocal() as session:
            return await session.get(Task, task_id)
    
    async def list_tasks(
        self,
        task_type: Optional[TaskType] = None,
        status: Optional[TaskStatus] = None,
        system_only: bool = False
    ) -> List[Task]:
        """List tasks with optional filtering."""
        async with AsyncSessionLocal() as session:
            query = select(Task)
            
            if task_type:
                query = query.where(Task.task_type == task_type)
            if status:
                query = query.where(Task.status == status)
            if system_only:
                query = query.where(Task.is_system_task == True)
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def get_task_executions(
        self,
        task_id: int,
        limit: int = 50
    ) -> List[TaskExecution]:
        """Get execution history for a task."""
        async with AsyncSessionLocal() as session:
            query = (
                select(TaskExecution)
                .where(TaskExecution.task_id == task_id)
                .order_by(TaskExecution.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def _load_and_schedule_tasks(self) -> None:
        """Load tasks from database and schedule active ones."""
        try:
            async with AsyncSessionLocal() as session:
                # Load active tasks
                query = select(Task).where(
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                )
                result = await session.execute(query)
                tasks = list(result.scalars().all())
                
                logger.info(f"Loading {len(tasks)} active tasks from database")
                
                for task in tasks:
                    try:
                        await self._schedule_task(task)
                    except Exception as e:
                        logger.error(f"Failed to schedule task {task.name}: {e}")
                        # Mark task as failed
                        task.status = TaskStatus.FAILED
                        await session.commit()
                        
        except Exception as e:
            logger.error(f"Failed to load tasks from database: {e}")
    
    async def _schedule_task(self, task: Task) -> None:
        """Schedule a single task with APScheduler."""
        if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            return
        
        try:
            # Create job wrapper function
            async def job_wrapper():
                context = await self.executor.execute_task(
                    task_id=task.id,
                    task_name=task.name,
                    function_args=task.function_args,
                    function_kwargs=task.function_kwargs,
                    metadata=task.task_metadata
                )
                
                # Update task status and last run time
                async with AsyncSessionLocal() as session:
                    db_task = await session.get(Task, task.id)
                    if db_task:
                        db_task.last_run_at = datetime.now(timezone.utc)
                        if task.task_type == TaskType.ONE_TIME:
                            db_task.status = TaskStatus.COMPLETED
                        await session.commit()
            
            # Handle different task types
            if task.task_type == TaskType.BACKGROUND:
                # Background tasks are handled differently
                await self.executor.execute_background_task(
                    task_id=task.id,
                    task_name=task.name,
                    function_args=task.function_args,
                    function_kwargs=task.function_kwargs,
                    metadata=task.task_metadata
                )
            else:
                # Schedule with APScheduler
                job_id = f"task_{task.id}"
                self.scheduler.add_job(
                    func=job_wrapper,
                    task_type=task.task_type,
                    job_id=job_id,
                    schedule_config=task.schedule_config,
                    max_instances=task.max_instances,
                    misfire_grace_time=task.misfire_grace_time,
                    jitter=task.jitter
                )
            
            # Update task status
            async with AsyncSessionLocal() as session:
                db_task = await session.get(Task, task.id)
                if db_task:
                    db_task.status = TaskStatus.RUNNING
                    await session.commit()
            
            logger.debug(f"Scheduled task: {task.name}")
            
        except Exception as e:
            logger.error(f"Failed to schedule task {task.name}: {e}")
            raise
    
    async def _unschedule_task(self, task: Task) -> None:
        """Unschedule a task."""
        try:
            job_id = f"task_{task.id}"
            
            if task.task_type == TaskType.BACKGROUND:
                # Cancel background task
                task_key = f"bg_{task.id}"
                await self.executor.cancel_background_task(task_key)
            else:
                # Remove from scheduler
                try:
                    self.scheduler.remove_job(job_id)
                except Exception:
                    # Job might not exist, that's okay
                    pass
            
            logger.debug(f"Unscheduled task: {task.name}")
            
        except Exception as e:
            logger.error(f"Failed to unschedule task {task.name}: {e}")
    
    async def _reschedule_task(self, task: Task) -> None:
        """Reschedule a task (unschedule then schedule)."""
        await self._unschedule_task(task)
        if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            await self._schedule_task(task)
    
    async def _maintenance_loop(self) -> None:
        """Background maintenance loop."""
        while self._running:
            try:
                # Clean up old execution records, update task statuses, etc.
                await asyncio.sleep(300)  # Run every 5 minutes
                
                # TODO: Implement maintenance tasks
                # - Clean up old execution records
                # - Update next_run_at timestamps
                # - Check for orphaned jobs
                # - Health checks
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in maintenance loop: {e}")
                await asyncio.sleep(60)  # Wait before retry