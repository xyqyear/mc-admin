"""Server restart schedule orchestration shared by lifecycle and HTTP callers."""

from fastapi import HTTPException
from pydantic import BaseModel

from app.cron.models import CronJobStatus

from ..cron import get_cron_manager, get_restart_scheduler
from ..cron.jobs.restart import ServerRestartParams
from ..cron.types import CronJobConfig, RegistrationStatus


class RestartScheduleResponse(BaseModel):
    """Response model for restart schedule information."""

    cronjob_id: str
    server_id: str
    name: str
    cron: str
    status: str
    registration_status: RegistrationStatus = "pending"
    registration_error: str | None = None
    next_run_time: str | None = None
    scheduled_time: str  # Human readable time like "06:15"


class RestartScheduleRequest(BaseModel):
    """Request model for creating/updating restart schedule."""

    custom_cron: str | None = (
        None  # Optional custom cron, if not provided, use auto-scheduled time
    )


async def get_managed_restart_schedule(server_id: str) -> CronJobConfig | None:
    try:
        return await get_cron_manager().get_managed_restart_schedule(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def schedule_auto_restart(
    server_id: str,
    request: RestartScheduleRequest,
) -> RestartScheduleResponse:
    """Create or update the server's active restart schedule."""
    schedule_name = f"restart-{server_id}"

    existing_job = await get_managed_restart_schedule(server_id)

    if request.custom_cron:
        cron_expr = request.custom_cron
    else:
        cron_expr = await get_restart_scheduler().generate_restart_cron(
            exclude_server_id=server_id
        )

    params = ServerRestartParams(server_id=server_id)

    if existing_job is not None:
        cronjob_id = existing_job.cronjob_id

        await get_cron_manager().update_cronjob(
            cronjob_id=cronjob_id,
            identifier="restart_server",
            params=params,
            cron=cron_expr,
        )

        if existing_job.status != CronJobStatus.ACTIVE:
            await get_cron_manager().resume_cronjob(cronjob_id)
    else:
        try:
            cronjob_id = await get_cron_manager().create_managed_restart_schedule(
                server_id=server_id, params=params, cron=cron_expr, name=schedule_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    job_config = await get_cron_manager().get_cronjob_config(cronjob_id)
    if not job_config:
        raise RuntimeError("无法读取已保存的重启计划")

    next_run_datetime = None
    if job_config.status == CronJobStatus.ACTIVE:
        try:
            next_run_datetime = await get_cron_manager().get_next_run_time(cronjob_id)
        except ValueError:
            pass

    next_run_time = (
        next_run_datetime.strftime("%Y-%m-%d %H:%M:%S") if next_run_datetime else None
    )

    cron_parts = job_config.cron.strip().split()
    if len(cron_parts) >= 2:
        minute, hour = cron_parts[0], cron_parts[1]
        if request.custom_cron is None and hour.isdigit() and minute.isdigit():
            scheduled_time = f"{int(hour):02d}:{int(minute):02d}"
        else:
            scheduled_time = f"{hour}:{minute.zfill(2)}"
    else:
        scheduled_time = "Custom"

    return RestartScheduleResponse(
        cronjob_id=cronjob_id,
        server_id=server_id,
        name=job_config.name,
        cron=job_config.cron,
        status=job_config.status.value,
        registration_status=job_config.registration_status,
        registration_error=job_config.registration_error,
        next_run_time=next_run_time,
        scheduled_time=scheduled_time,
    )
