"""Simplified task management system for MC Admin."""

import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .models import AsyncFunc, TaskInfo, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class TaskManager:
    """Simplified task manager for runtime task execution."""

    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    async def start(self) -> None:
        """Start the task manager."""
        if self._running:
            logger.warning("TaskManager is already running")
            return

        logger.info("Starting TaskManager")

        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()

        self._running = True
        logger.info("TaskManager started successfully")

    def is_running(self) -> bool:
        """Check if the task manager is running."""
        return self._running

    def submit_task(
        self, 
        func: AsyncFunc, 
        task_name: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TaskInfo:
        """Submit a task for immediate execution.

        Args:
            func: The async function to execute
            task_name: Name for the task (for logging and tracking)
            description: Optional description of the task
            metadata: Optional metadata dictionary

        Returns:
            TaskInfo: Task information for tracking

        Raises:
            RuntimeError: If task manager is not running
        """
        if not self._running:
            raise RuntimeError("TaskManager is not running")

        task_id = str(uuid.uuid4())
        task_info = TaskInfo(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.RUNNING,
            task_type=TaskType.ONESHOT,
            created_at=datetime.now(timezone.utc),
            description=description,
            metadata=metadata or {}
        )

        self._tasks[task_id] = task_info

        # Create and start the async task
        async_task = asyncio.create_task(self._execute_task(func, task_info))
        self._running_tasks[task_id] = async_task

        logger.info(f"Submitted task: {task_name} (ID: {task_id})")
        return task_info

    def schedule_task(
        self,
        func: AsyncFunc,
        task_name: str,
        cron_expression: Optional[str] = None,
        interval_seconds: Optional[int] = None,
        start_time: Optional[datetime] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TaskInfo:
        """Schedule a task for future execution.

        Args:
            func: The async function to execute
            task_name: Name for the task
            cron_expression: Cron expression for scheduling (e.g., "0 2 * * *")
            interval_seconds: Interval in seconds for repeated execution
            start_time: When to start the scheduled task
            description: Optional description of the task
            metadata: Optional metadata dictionary

        Returns:
            TaskInfo: Task information for tracking

        Raises:
            RuntimeError: If task manager is not running
            ValueError: If neither cron_expression nor interval_seconds is provided
        """
        if not self._running:
            raise RuntimeError("TaskManager is not running")

        if not cron_expression and not interval_seconds:
            raise ValueError(
                "Either cron_expression or interval_seconds must be provided"
            )

        if not self._scheduler:
            raise RuntimeError("Scheduler is not available")

        task_id = str(uuid.uuid4())
        
        # Calculate next run time
        now = datetime.now(timezone.utc)
        next_run = start_time or now
        
        task_info = TaskInfo(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.RUNNING,
            task_type=TaskType.SCHEDULED,
            created_at=now,
            description=description,
            metadata=metadata or {},
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            start_time=start_time,
            next_run_at=next_run
        )

        self._tasks[task_id] = task_info

        # Create trigger
        if cron_expression:
            trigger = CronTrigger.from_crontab(cron_expression)
        else:
            trigger = IntervalTrigger(seconds=interval_seconds or 60)  # Default to 60 seconds

        # Schedule the task
        self._scheduler.add_job(
            func=self._execute_scheduled_task,
            trigger=trigger,
            args=[func, task_info],
            id=task_id,
            name=task_name,
            start_date=start_time,
        )

        logger.info(f"Scheduled task: {task_name} (ID: {task_id}, Trigger: {trigger})")
        return task_info

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            bool: True if task was cancelled, False if not found
        """
        # Cancel async task
        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            task.cancel()
            del self._running_tasks[task_id]
            logger.info(f"Cancelled async task: {task_id}")

        # Cancel scheduled task
        if self._scheduler:
            try:
                self._scheduler.remove_job(task_id)
                logger.info(f"Cancelled scheduled task: {task_id}")
            except Exception:
                pass  # Job might not exist in scheduler

        # Update task status
        if task_id in self._tasks:
            task_info = self._tasks[task_id]
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now(timezone.utc)
            return True

        return False

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task information by ID.

        Args:
            task_id: ID of the task to retrieve

        Returns:
            TaskInfo: Task information if found, None otherwise
        """
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[TaskInfo]:
        """Get information for all tasks.

        Returns:
            List[TaskInfo]: List of all task information
        """
        return list(self._tasks.values())

    def get_scheduled_tasks(self) -> List[TaskInfo]:
        """Get all scheduled/recurring tasks.

        Returns:
            List[TaskInfo]: List of scheduled tasks
        """
        return [task for task in self._tasks.values() if task.task_type == TaskType.SCHEDULED]

    def get_oneshot_tasks(self) -> List[TaskInfo]:
        """Get all one-time tasks.

        Returns:
            List[TaskInfo]: List of one-time tasks
        """
        return [task for task in self._tasks.values() if task.task_type == TaskType.ONESHOT]

    def get_task_schedule_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed schedule information for a task.

        Args:
            task_id: ID of the task to get schedule info for

        Returns:
            Dict containing schedule information, or None if task not found
        """
        task = self._tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "task_name": task.task_name,
            "task_type": task.task_type,
            "cron_expression": task.cron_expression,
            "interval_seconds": task.interval_seconds,
            "next_run_at": task.next_run_at,
            "last_run_at": task.last_run_at,
            "execution_count": task.execution_count,
            "start_time": task.start_time
        }

    async def _execute_task(self, func: AsyncFunc, task_info: TaskInfo) -> None:
        """Execute a task function and update task info.

        Args:
            func: The async function to execute
            task_info: Task information to update
        """
        try:
            logger.info(
                f"Starting task execution: {task_info.task_name} (ID: {task_info.task_id})"
            )

            # Execute the function
            result = await func()

            # Update task info on success
            task_info.status = TaskStatus.COMPLETED
            task_info.completed_at = datetime.now(timezone.utc)
            task_info.result = result
            task_info.execution_count += 1
            task_info.last_run_at = task_info.completed_at

            logger.info(
                f"Task execution completed: {task_info.task_name} (ID: {task_info.task_id})"
            )

        except asyncio.CancelledError:
            # Task was cancelled
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now(timezone.utc)
            logger.info(
                f"Task execution cancelled: {task_info.task_name} (ID: {task_info.task_id})"
            )
            raise

        except Exception as e:
            # Task failed
            error_message = str(e)
            error_traceback = traceback.format_exc()

            task_info.status = TaskStatus.FAILED
            task_info.completed_at = datetime.now(timezone.utc)
            task_info.error_message = error_message

            logger.error(
                f"Task execution failed: {task_info.task_name} (ID: {task_info.task_id}): {error_message}"
            )
            logger.debug(f"Task failure traceback:\n{error_traceback}")

        finally:
            # Remove from running tasks
            self._running_tasks.pop(task_info.task_id, None)

    async def _execute_scheduled_task(
        self, func: AsyncFunc, task_info: TaskInfo
    ) -> None:
        """Execute a scheduled task function.

        Args:
            func: The async function to execute
            task_info: Task information (for logging context)
        """
        try:
            logger.info(
                f"Executing scheduled task: {task_info.task_name} (ID: {task_info.task_id})"
            )
            await func()
            
            # Update execution statistics
            task_info.execution_count += 1
            task_info.last_run_at = datetime.now(timezone.utc)
            
            logger.info(
                f"Scheduled task completed: {task_info.task_name} (ID: {task_info.task_id})"
            )

        except Exception as e:
            error_message = str(e)
            error_traceback = traceback.format_exc()

            logger.error(
                f"Scheduled task failed: {task_info.task_name} (ID: {task_info.task_id}): {error_message}"
            )
            logger.debug(f"Scheduled task failure traceback:\n{error_traceback}")
