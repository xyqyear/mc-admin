"""HTTP contracts for scheduled jobs."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..self_check.job import SelfCheckJobParams
from .jobs.backup import BackupJobParams
from .jobs.restart import ServerRestartParams
from .types import RegistrationStatus


class CronJobInput(BaseModel):
    cron: str
    cronjob_id: str | None = None
    name: str | None = None
    second: str | None = None


class RestartCronJobInput(CronJobInput):
    identifier: Literal["restart_server"]
    params: ServerRestartParams


class BackupCronJobInput(CronJobInput):
    identifier: Literal["backup"]
    params: BackupJobParams


class SelfCheckCronJobInput(CronJobInput):
    identifier: Literal["self_check"]
    params: SelfCheckJobParams


CreateCronJobRequest = Annotated[
    RestartCronJobInput | BackupCronJobInput | SelfCheckCronJobInput,
    Field(discriminator="identifier"),
]
UpdateCronJobRequest = CreateCronJobRequest


class CronJobResponse(BaseModel):
    """Response model for cron job information."""

    cronjob_id: str
    identifier: str
    name: str
    cron: str
    second: str | None = None
    params: dict
    execution_count: int
    is_system: bool
    status: str
    registration_status: RegistrationStatus = "pending"
    registration_error: str | None = None
    created_at: datetime
    updated_at: datetime
    managed_purpose: str | None = None


class CronJobExecutionResponse(BaseModel):
    """Response model for cron job execution information."""

    execution_id: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    status: str
    messages: list[str]


class CronJobNextRunTimeResponse(BaseModel):
    """Response model for cron job next run time."""

    cronjob_id: str
    next_run_time: datetime


class RegisteredCronJobResponse(BaseModel):
    """Response model for registered cron job information."""

    identifier: str
    description: str
    is_system: bool
    default_cron: str | None = None
    default_second: str | None = None
    default_params: dict | None = None
    default_name: str | None = None
