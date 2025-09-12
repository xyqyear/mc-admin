"""Task system data models for MC Admin."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base


class TaskType(str, Enum):
    """Task type enumeration."""
    ONE_TIME = "one_time"
    RECURRING = "recurring"
    BACKGROUND = "background"


class TaskStatus(str, Enum):
    """Task status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskExecutionStatus(str, Enum):
    """Task execution status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Base):
    """Task table ORM model."""
    
    __tablename__ = "tasks"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    task_type: Mapped[TaskType] = mapped_column(SQLAlchemyEnum(TaskType))
    status: Mapped[TaskStatus] = mapped_column(
        SQLAlchemyEnum(TaskStatus), default=TaskStatus.PENDING
    )
    
    # Function details - function is now stored in registry, not database
    function_args: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    function_kwargs: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    
    # Scheduling details
    schedule_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)  # APScheduler trigger config
    max_instances: Mapped[int] = mapped_column(default=1)  # Max concurrent instances
    misfire_grace_time: Mapped[Optional[int]] = mapped_column()  # Seconds
    jitter: Mapped[Optional[int]] = mapped_column()  # Seconds
    
    # Metadata and configuration
    task_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    is_system_task: Mapped[bool] = mapped_column(default=False)  # System vs user task
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Created by user (optional, for user-created tasks)
    created_by_user_id: Mapped[Optional[int]] = mapped_column()


class TaskExecution(Base):
    """Task execution history table ORM model."""
    
    __tablename__ = "task_executions"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(index=True)  # Foreign key to Task
    execution_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # UUID
    
    status: Mapped[TaskExecutionStatus] = mapped_column(
        SQLAlchemyEnum(TaskExecutionStatus), default=TaskExecutionStatus.PENDING
    )
    
    # Execution details
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[float]] = mapped_column()
    
    # Results and errors
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_traceback: Mapped[Optional[str]] = mapped_column(Text)
    
    # APScheduler job details
    apscheduler_job_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Metadata
    execution_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# Pydantic models for request/response serialization

class TaskBase(BaseModel):
    """Base Pydantic model for Task."""
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    task_type: TaskType
    function_args: Optional[Dict[str, Any]] = Field(default_factory=dict)
    function_kwargs: Optional[Dict[str, Any]] = Field(default_factory=dict)
    schedule_config: Optional[Dict[str, Any]] = None
    max_instances: int = Field(default=1, ge=1)
    misfire_grace_time: Optional[int] = Field(default=None, ge=0)
    jitter: Optional[int] = Field(default=None, ge=0)
    task_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TaskCreate(TaskBase):
    """Task creation model."""
    pass


class TaskUpdate(BaseModel):
    """Task update model."""
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    schedule_config: Optional[Dict[str, Any]] = None
    max_instances: Optional[int] = Field(default=None, ge=1)
    misfire_grace_time: Optional[int] = Field(default=None, ge=0)
    jitter: Optional[int] = Field(default=None, ge=0)
    task_metadata: Optional[Dict[str, Any]] = None


class TaskPublic(TaskBase):
    """Public Task model for API responses."""
    id: int
    status: TaskStatus
    is_system_task: bool
    created_at: datetime
    updated_at: datetime
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    created_by_user_id: Optional[int]


class TaskExecutionBase(BaseModel):
    """Base Pydantic model for TaskExecution."""
    task_id: int
    execution_id: str
    apscheduler_job_id: Optional[str] = None
    execution_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TaskExecutionCreate(TaskExecutionBase):
    """Task execution creation model."""
    pass


class TaskExecutionUpdate(BaseModel):
    """Task execution update model."""
    status: Optional[TaskExecutionStatus] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None


class TaskExecutionPublic(TaskExecutionBase):
    """Public TaskExecution model for API responses."""
    id: int
    status: TaskExecutionStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    error_traceback: Optional[str]
    created_at: datetime