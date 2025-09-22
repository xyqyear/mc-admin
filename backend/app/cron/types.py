"""
Type definitions for the cron job management system.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, List, Optional, Type

from pydantic import BaseModel, Field

from ..dynamic_config.schemas import BaseConfigSchema
from ..models import CronJobStatus, ExecutionStatus

# Type alias for async cron job functions
AsyncCronJobFunction = Callable[["ExecutionContext"], Awaitable[None]]


@dataclass(frozen=True)
class CronJobRegistration:
    """
    Frozen dataclass representing a registered cron job with its metadata.

    This replaces the tuple (function, description, schema_cls) for better type safety.
    """

    function: AsyncCronJobFunction
    description: str
    schema_cls: Type[BaseConfigSchema]


class ExecutionContext(BaseModel):
    """
    Execution context for a single cron job execution.

    This context is created for each cron job execution and contains all the
    information needed during execution, including parameters, logging,
    and execution metadata.
    """

    cronjob_id: str
    identifier: str
    execution_id: str
    params: BaseConfigSchema
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    status: ExecutionStatus = ExecutionStatus.RUNNING
    messages: List[str] = Field(default_factory=list)

    def log(self, message: str) -> None:
        """
        Add a log message to the execution context.

        Args:
            message: The message to log
        """
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.messages.append(f"[{timestamp}] {message}")

    def to_execution_record(self) -> dict:
        """
        Convert the execution context to a dictionary for database storage.

        Returns:
            Dictionary containing execution record data
        """
        return {
            "cronjob_id": self.cronjob_id,
            "execution_id": self.execution_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "messages_json": json.dumps(self.messages, ensure_ascii=False),
        }


class CronJobConfig(BaseModel):
    """
    CronJob configuration model for in-memory representation.

    This represents a complete cron job configuration including parameters,
    scheduling information, and metadata.
    """

    cronjob_id: str
    identifier: str
    name: str
    cron: str
    second: Optional[str] = None
    params: BaseConfigSchema
    execution_count: int = 0
    status: CronJobStatus = CronJobStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    class Config:
        arbitrary_types_allowed = True


@dataclass(frozen=True)
class CronJobExecutionRecord:
    """
    Frozen dataclass representing a cron job execution record.

    This is returned by get_execution_history instead of dictionaries.
    """

    cronjob_id: str
    execution_id: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_ms: Optional[int]
    status: ExecutionStatus
    messages: List[str]
