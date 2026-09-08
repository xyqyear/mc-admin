"""
Server restart schedule management API endpoints.
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import status as http_status

from ...cron import cron_manager
from ...dependencies import get_current_user
from ...models import CronJobStatus, UserPublic
from ...servers.restart_schedule import (
    RestartScheduleRequest,
    RestartScheduleResponse,
    schedule_auto_restart,
)

router = APIRouter(
    prefix="/servers",
    tags=["server-restart-schedule"],
)


@router.post("/{server_id}/restart-schedule", response_model=RestartScheduleResponse)
async def create_or_update_restart_schedule(
    server_id: str,
    request: RestartScheduleRequest = Body(
        default_factory=RestartScheduleRequest,
        json_schema_extra={"default": {}},
    ),
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Create or update a restart schedule for a server.

    - If a restart schedule already exists, it will be updated and resumed
    - If no schedule exists, a new one will be created
    - If custom_cron is not provided, uses the automatic conflict-free time slot finder
    """
    return await schedule_auto_restart(server_id, request)


@router.get(
    "/{server_id}/restart-schedule", response_model=RestartScheduleResponse | None
)
async def get_restart_schedule(
    server_id: str,
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Get the current restart schedule for a server.

    Returns None if no restart schedule exists.
    """
    schedule_name = f"restart-{server_id}"

    # Find existing restart schedule
    existing_jobs = await cron_manager.get_all_cronjobs(
        identifier="restart_server", name=schedule_name
    )

    if not existing_jobs:
        return None

    job_config = existing_jobs[0]

    # Parse scheduled time from cron
    cron_parts = job_config.cron.strip().split()
    if len(cron_parts) >= 2:
        minute, hour = cron_parts[0], cron_parts[1]
        scheduled_time = f"{hour}:{minute.zfill(2)}"
    else:
        scheduled_time = "Custom"

    # Get next run time if job is active
    next_run_time = None
    if job_config.status == CronJobStatus.ACTIVE:
        try:
            next_run_datetime = await cron_manager.get_next_run_time(
                job_config.cronjob_id
            )
            next_run_time = (
                next_run_datetime.strftime("%Y-%m-%d %H:%M:%S")
                if next_run_datetime
                else None
            )
        except ValueError:
            pass

    return RestartScheduleResponse(
        cronjob_id=job_config.cronjob_id,
        server_id=server_id,
        name=schedule_name,
        cron=job_config.cron,
        status=job_config.status.value,
        next_run_time=next_run_time,
        scheduled_time=scheduled_time,
    )


@router.delete("/{server_id}/restart-schedule")
async def delete_restart_schedule(
    server_id: str,
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Delete the restart schedule for a server.
    """
    schedule_name = f"restart-{server_id}"

    # Find existing restart schedule
    existing_jobs = await cron_manager.get_all_cronjobs(
        identifier="restart_server", name=schedule_name
    )

    if not existing_jobs:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No restart schedule found for server '{server_id}'",
        )

    job_config = existing_jobs[0]

    # Cancel the cron job
    await cron_manager.cancel_cronjob(job_config.cronjob_id)

    return {"message": f"Restart schedule for server '{server_id}' has been deleted"}


@router.post("/{server_id}/restart-schedule/pause")
async def pause_restart_schedule(
    server_id: str,
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Pause the restart schedule for a server.
    """
    schedule_name = f"restart-{server_id}"

    # Find existing restart schedule
    existing_jobs = await cron_manager.get_all_cronjobs(
        identifier="restart_server", name=schedule_name
    )

    if not existing_jobs:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No restart schedule found for server '{server_id}'",
        )

    job_config = existing_jobs[0]

    # Pause the cron job
    await cron_manager.pause_cronjob(job_config.cronjob_id)

    return {"message": f"Restart schedule for server '{server_id}' has been paused"}


@router.post("/{server_id}/restart-schedule/resume")
async def resume_restart_schedule(
    server_id: str,
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Resume the restart schedule for a server.
    """
    schedule_name = f"restart-{server_id}"

    # Find existing restart schedule
    existing_jobs = await cron_manager.get_all_cronjobs(
        identifier="restart_server", name=schedule_name
    )

    if not existing_jobs:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No restart schedule found for server '{server_id}'",
        )

    job_config = existing_jobs[0]

    # Resume the cron job
    await cron_manager.resume_cronjob(job_config.cronjob_id)

    return {"message": f"Restart schedule for server '{server_id}' has been resumed"}
