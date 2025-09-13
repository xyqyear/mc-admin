"""Simplified task system data models for MC Admin."""

from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Dict

# Type alias for async functions
AsyncFunc = Callable[[], Awaitable[Any]]


class TaskStatus(str, Enum):
    """Task status enumeration."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Task type enumeration."""
    ONESHOT = "oneshot"      # One-time task
    SCHEDULED = "scheduled"  # Scheduled/recurring task


@dataclass
class TaskInfo:
    """Task information dataclass for runtime tracking."""
    # Basic task identification
    task_id: str
    task_name: str
    status: TaskStatus
    task_type: TaskType
    created_at: datetime
    
    # Task description and metadata
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    
    # Execution information
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[Any] = None
    execution_count: int = 0
    last_run_at: Optional[datetime] = None
    
    # Scheduling information (for scheduled tasks)
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    next_run_at: Optional[datetime] = None
    start_time: Optional[datetime] = None