"""
Type definitions for the cron job management system.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.cron.models import CronJobStatus, ExecutionStatus

from ..dynamic_config.schemas import BaseConfigSchema

RegistrationStatus = Literal["registered", "pending", "failed", "blocked", "inactive"]

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
    schema_cls: type[BaseConfigSchema]
    is_system: bool = False
    default_cron: str | None = None
    default_second: str | None = None
    default_params: BaseConfigSchema | None = None
    default_name: str | None = None


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
    managed_server_generation: int | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    status: ExecutionStatus = ExecutionStatus.RUNNING
    messages: list[str] = Field(default_factory=list)

    def skip(self, reason: str) -> None:
        self.status = ExecutionStatus.SKIPPED
        self.log(reason)

    def log(self, message: str) -> None:
        """
        Add a log message to the execution context.

        Args:
            message: The message to log
        """
        timestamp = datetime.now(UTC).astimezone().strftime("%H:%M:%S.%f")[:-3]
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
    second: str | None = None
    params: BaseConfigSchema
    execution_count: int = 0
    managed_server_generation: int | None = None
    managed_purpose: str | None = None
    managed_binding_issue: str | None = None
    is_system: bool = False
    status: CronJobStatus = CronJobStatus.ACTIVE
    registration_status: RegistrationStatus = "pending"
    registration_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(arbitrary_types_allowed=True)


@dataclass(frozen=True)
class CronJobExecutionRecord:
    """
    Frozen dataclass representing a cron job execution record.

    This is returned by get_execution_history instead of dictionaries.
    """

    cronjob_id: str
    execution_id: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    status: ExecutionStatus
    messages: list[str]
