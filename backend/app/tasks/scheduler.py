"""APScheduler wrapper for task scheduling."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .models import TaskType

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Wrapper around APScheduler AsyncIOScheduler for task management."""
    
    def __init__(self):
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler is already running")
            return
            
        logger.info("Starting TaskScheduler")
        self._scheduler = AsyncIOScheduler()
        
        try:
            self._scheduler.start()
            self._running = True
            logger.info("TaskScheduler started successfully")
        except Exception as e:
            logger.error(f"Failed to start TaskScheduler: {e}")
            self._scheduler = None
            raise
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running or not self._scheduler:
            logger.warning("Scheduler is not running")
            return
            
        logger.info("Stopping TaskScheduler")
        try:
            self._scheduler.shutdown()
            self._running = False
            self._scheduler = None
            logger.info("TaskScheduler stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping TaskScheduler: {e}")
            raise
    
    @asynccontextmanager
    async def lifespan(self):
        """Context manager for scheduler lifecycle."""
        await self.start()
        try:
            yield self
        finally:
            await self.stop()
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running and self._scheduler is not None
    
    def add_job(
        self,
        func,
        task_type: TaskType,
        job_id: str,
        schedule_config: Optional[Dict[str, Any]] = None,
        max_instances: int = 1,
        misfire_grace_time: Optional[int] = None,
        jitter: Optional[int] = None,
        **kwargs
    ) -> str:
        """Add a job to the scheduler.
        
        Args:
            func: The function to execute
            task_type: Type of task (ONE_TIME, RECURRING, BACKGROUND)
            job_id: Unique identifier for the job
            schedule_config: Trigger configuration
            max_instances: Maximum concurrent instances
            misfire_grace_time: Grace time for misfired jobs in seconds
            jitter: Random delay in seconds
            **kwargs: Additional arguments passed to the function
            
        Returns:
            The job ID
            
        Raises:
            RuntimeError: If scheduler is not running
            ValueError: If invalid schedule configuration
        """
        if not self.is_running():
            raise RuntimeError("Scheduler is not running")
        
        trigger = self._create_trigger(task_type, schedule_config)
        
        # Build job configuration
        job_config = {
            "func": func,
            "trigger": trigger,
            "id": job_id,
            "max_instances": max_instances,
            "kwargs": kwargs,
        }
        
        if misfire_grace_time is not None:
            job_config["misfire_grace_time"] = misfire_grace_time
            
        if jitter is not None:
            job_config["jitter"] = jitter
        
        try:
            job = self._scheduler.add_job(**job_config)
            logger.info(f"Added job {job_id} with trigger {trigger}")
            return job.id
        except Exception as e:
            logger.error(f"Failed to add job {job_id}: {e}")
            raise
    
    def remove_job(self, job_id: str) -> None:
        """Remove a job from the scheduler."""
        if not self.is_running():
            raise RuntimeError("Scheduler is not running")
        
        try:
            self._scheduler.remove_job(job_id)
            logger.info(f"Removed job {job_id}")
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            # Don't raise if job doesn't exist
            pass
    
    def pause_job(self, job_id: str) -> None:
        """Pause a job."""
        if not self.is_running():
            raise RuntimeError("Scheduler is not running")
        
        try:
            self._scheduler.pause_job(job_id)
            logger.info(f"Paused job {job_id}")
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")
            raise
    
    def resume_job(self, job_id: str) -> None:
        """Resume a paused job."""
        if not self.is_running():
            raise RuntimeError("Scheduler is not running")
        
        try:
            self._scheduler.resume_job(job_id)
            logger.info(f"Resumed job {job_id}")
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")
            raise
    
    def run_job_now(self, job_id: str, **kwargs) -> None:
        """Execute a job immediately."""
        if not self.is_running():
            raise RuntimeError("Scheduler is not running")
        
        try:
            job = self._scheduler.get_job(job_id)
            if job:
                job.modify(next_run_time=None)  # Run immediately
                logger.info(f"Scheduled immediate execution of job {job_id}")
            else:
                logger.error(f"Job {job_id} not found")
        except Exception as e:
            logger.error(f"Failed to run job {job_id}: {e}")
            raise
    
    def _create_trigger(self, task_type: TaskType, schedule_config: Optional[Dict[str, Any]]):
        """Create appropriate trigger based on task type and configuration."""
        if task_type == TaskType.ONE_TIME:
            if not schedule_config:
                # Run immediately
                return DateTrigger()
            
            if "run_date" in schedule_config:
                return DateTrigger(**schedule_config)
            else:
                # Default to immediate execution
                return DateTrigger()
                
        elif task_type == TaskType.RECURRING:
            if not schedule_config:
                raise ValueError("RECURRING tasks require schedule_config")
            
            # Determine trigger type from config
            if "cron" in schedule_config:
                # Cron-style scheduling
                cron_config = schedule_config["cron"]
                return CronTrigger(**cron_config)
            elif "interval" in schedule_config:
                # Interval-based scheduling
                interval_config = schedule_config["interval"]
                return IntervalTrigger(**interval_config)
            else:
                raise ValueError("RECURRING tasks require 'cron' or 'interval' in schedule_config")
                
        elif task_type == TaskType.BACKGROUND:
            # Background tasks run immediately and typically manage their own lifecycle
            return DateTrigger()
            
        else:
            raise ValueError(f"Unsupported task type: {task_type}")
    
    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a scheduled job."""
        if not self.is_running():
            return None
        
        try:
            job = self._scheduler.get_job(job_id)
            if job:
                return {
                    "id": job.id,
                    "next_run_time": job.next_run_time,
                    "trigger": str(job.trigger),
                    "max_instances": job.max_instances,
                    # Note: APScheduler 3.x doesn't have paused attribute on jobs
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get job info for {job_id}: {e}")
            return None
    
    def get_all_jobs(self) -> list[Dict[str, Any]]:
        """Get information about all scheduled jobs."""
        if not self.is_running():
            return []
        
        try:
            jobs = self._scheduler.get_jobs()
            job_info = []
            for job in jobs:
                job_info.append({
                    "id": job.id,
                    "next_run_time": job.next_run_time,
                    "trigger": str(job.trigger),
                    "max_instances": job.max_instances,
                    # Note: APScheduler 3.x doesn't have paused attribute on jobs
                })
            return job_info
        except Exception as e:
            logger.error(f"Failed to get all jobs: {e}")
            return []