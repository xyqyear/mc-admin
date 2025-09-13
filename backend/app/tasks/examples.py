"""Examples of using the simplified task system.

This module demonstrates how to use the TaskManager for various task scenarios:
- One-time tasks  
- Background monitoring tasks
- Scheduled tasks with cron expressions
- Tasks with parameters using functools.partial
"""

import asyncio
import logging
from datetime import datetime, timezone
from functools import partial

from . import TaskManager

logger = logging.getLogger(__name__)


# Example task functions

async def hello_world() -> str:
    """Simple greeting task."""
    logger.info("Hello, World!")
    await asyncio.sleep(1)  # Simulate some work
    return "Hello task completed"


async def process_data(data_id: str, process_type: str) -> dict:
    """Example data processing task with parameters."""
    logger.info(f"Processing data {data_id} with type {process_type}")
    await asyncio.sleep(2)  # Simulate processing
    return {
        "data_id": data_id,
        "process_type": process_type,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed"
    }


async def system_monitor() -> None:
    """Background monitoring task that runs continuously."""
    iteration = 0
    while True:
        iteration += 1
        logger.info(f"System monitoring check #{iteration}")
        
        # Simulate monitoring logic
        await asyncio.sleep(30)  # Check every 30 seconds
        
        # In a real scenario, you might want to break on certain conditions
        # For this example, we'll run indefinitely


async def daily_backup() -> str:
    """Daily backup task."""
    logger.info("Performing daily backup...")
    await asyncio.sleep(3)  # Simulate backup process
    backup_time = datetime.now(timezone.utc).isoformat()
    logger.info(f"Daily backup completed at {backup_time}")
    return f"Backup completed at {backup_time}"


async def cleanup_temp_files(directory: str, older_than_days: int) -> dict:
    """Cleanup task with parameters."""
    logger.info(f"Cleaning up temp files in {directory} older than {older_than_days} days")
    await asyncio.sleep(1)  # Simulate cleanup
    return {
        "directory": directory,
        "older_than_days": older_than_days,
        "files_cleaned": 42,  # Mock result
        "cleaned_at": datetime.now(timezone.utc).isoformat()
    }


async def failing_task() -> None:
    """Example task that demonstrates error handling."""
    logger.info("This task will fail...")
    await asyncio.sleep(1)
    raise ValueError("This is an intentional error for demonstration")


# Example usage functions

async def demonstrate_basic_usage():
    """Demonstrate basic task submission and management."""
    manager = TaskManager()
    await manager.start()
    
    try:
        logger.info("=== Basic Task Submission Demo ===")
        
        # Submit a simple task with description
        task_info = manager.submit_task(
            hello_world, 
            "greeting_task",
            description="Simple greeting task for demonstration",
            metadata={"priority": "low", "category": "demo"}
        )
        logger.info(f"Submitted task: {task_info.task_id}")
        logger.info(f"Task description: {task_info.description}")
        logger.info(f"Task metadata: {task_info.metadata}")
        
        # Wait a moment and check status
        await asyncio.sleep(2)
        updated_info = manager.get_task(task_info.task_id)
        if updated_info:
            logger.info(f"Task status: {updated_info.status}")
            logger.info(f"Execution count: {updated_info.execution_count}")
            if updated_info.result:
                logger.info(f"Task result: {updated_info.result}")
        
        # Submit a task with parameters using partial and rich metadata
        process_func = partial(process_data, "data123", "batch_process")
        task_info2 = manager.submit_task(
            process_func, 
            "data_processing",
            description="Process data with ID data123 using batch processing method",
            metadata={
                "data_id": "data123", 
                "process_type": "batch_process",
                "priority": "high",
                "owner": "system"
            }
        )
        logger.info(f"Submitted processing task: {task_info2.task_id}")
        
        # Wait and check result
        await asyncio.sleep(3)
        updated_info2 = manager.get_task(task_info2.task_id)
        if updated_info2:
            logger.info(f"Processing task status: {updated_info2.status}")
            logger.info(f"Processing task execution count: {updated_info2.execution_count}")
            logger.info(f"Processing task last run: {updated_info2.last_run_at}")
            if updated_info2.result:
                logger.info(f"Processing result: {updated_info2.result}")
        
    finally:
        await manager.stop()


async def demonstrate_background_task():
    """Demonstrate background task that runs continuously."""
    manager = TaskManager()
    await manager.start()
    
    try:
        logger.info("=== Background Task Demo ===")
        
        # Submit a background monitoring task
        monitor_info = manager.submit_task(system_monitor, "system_monitor")
        logger.info(f"Started background monitor: {monitor_info.task_id}")
        
        # Let it run for a while
        logger.info("Letting background task run for 2 minutes...")
        await asyncio.sleep(120)
        
        # Cancel the background task
        success = manager.cancel_task(monitor_info.task_id)
        logger.info(f"Background task cancelled: {success}")
        
    finally:
        await manager.stop()


async def demonstrate_scheduled_tasks():
    """Demonstrate scheduled task execution."""
    manager = TaskManager()
    await manager.start()
    
    try:
        logger.info("=== Scheduled Task Demo ===")
        
        # Schedule a task to run every 10 seconds with detailed metadata
        frequent_task = manager.schedule_task(
            hello_world, 
            "frequent_greeting",
            interval_seconds=10,
            description="Frequent greeting task that runs every 10 seconds",
            metadata={"interval": 10, "type": "greeting", "priority": "low"}
        )
        logger.info(f"Scheduled frequent task: {frequent_task.task_id}")
        logger.info(f"Task type: {frequent_task.task_type}")
        logger.info(f"Interval: {frequent_task.interval_seconds} seconds")
        
        # Schedule a cleanup task to run every minute using cron
        cleanup_func = partial(cleanup_temp_files, "/tmp", 7)
        cleanup_task = manager.schedule_task(
            cleanup_func,
            "temp_cleanup", 
            cron_expression="* * * * *",  # Every minute
            description="Cleanup temporary files older than 7 days",
            metadata={"directory": "/tmp", "max_age_days": 7, "type": "maintenance"}
        )
        logger.info(f"Scheduled cleanup task: {cleanup_task.task_id}")
        logger.info(f"Cron expression: {cleanup_task.cron_expression}")
        
        # Schedule a daily backup (for demo, we'll use a short interval)
        backup_task = manager.schedule_task(
            daily_backup,
            "daily_backup",
            interval_seconds=30,  # Every 30 seconds for demo
            description="Daily backup task (demo with 30s interval)",
            metadata={"backup_type": "daily", "retention_days": 30}
        )
        logger.info(f"Scheduled backup task: {backup_task.task_id}")
        
        # Get detailed schedule information
        backup_schedule_info = manager.get_task_schedule_info(backup_task.task_id)
        if backup_schedule_info:
            logger.info("Backup task schedule info:")
            logger.info(f"  Next run: {backup_schedule_info['next_run_at']}")
            logger.info(f"  Execution count: {backup_schedule_info['execution_count']}")
        
        # Let scheduled tasks run for a while
        logger.info("Letting scheduled tasks run for 2 minutes...")
        await asyncio.sleep(120)
        
        # Show all tasks with enhanced information
        all_tasks = manager.get_all_tasks()
        scheduled_tasks = manager.get_scheduled_tasks()
        oneshot_tasks = manager.get_oneshot_tasks()
        
        logger.info(f"Total tasks: {len(all_tasks)}")
        logger.info(f"Scheduled tasks: {len(scheduled_tasks)}")
        logger.info(f"One-shot tasks: {len(oneshot_tasks)}")
        
        for task in all_tasks:
            logger.info(f"  Task {task.task_name}: {task.status} (type: {task.task_type})")
            logger.info(f"    Executions: {task.execution_count}, Last run: {task.last_run_at}")
            if task.description:
                logger.info(f"    Description: {task.description}")
            if task.metadata:
                logger.info(f"    Metadata: {task.metadata}")
        
    finally:
        await manager.stop()


async def demonstrate_error_handling():
    """Demonstrate task error handling."""
    manager = TaskManager()
    await manager.start()
    
    try:
        logger.info("=== Error Handling Demo ===")
        
        # Submit a task that will fail
        failing_info = manager.submit_task(failing_task, "failing_task")
        logger.info(f"Submitted failing task: {failing_info.task_id}")
        
        # Wait for it to fail
        await asyncio.sleep(2)
        
        # Check the error
        updated_info = manager.get_task(failing_info.task_id)
        if updated_info:
            logger.info(f"Failed task status: {updated_info.status}")
            if updated_info.error_message:
                logger.error(f"Error message: {updated_info.error_message}")
        
    finally:
        await manager.stop()


async def main():
    """Run all demonstrations."""
    logger.info("Starting task system demonstrations...")
    
    await demonstrate_basic_usage()
    await asyncio.sleep(1)  # Brief pause between demos
    
    await demonstrate_scheduled_tasks()
    await asyncio.sleep(1)
    
    await demonstrate_error_handling()
    await asyncio.sleep(1)
    
    # Note: Background task demo is commented out as it runs for 2 minutes
    # await demonstrate_background_task()
    
    logger.info("All demonstrations completed!")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())