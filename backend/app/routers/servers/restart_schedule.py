"""
Server restart schedule management API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel

from ...cron import RestartScheduler, cron_manager
from ...cron.jobs.restart import ServerRestartParams
from ...dependencies import get_current_user
from ...models import CronJobStatus, UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["server-restart-schedule"],
)


class RestartScheduleResponse(BaseModel):
    """Response model for restart schedule information."""

    cronjob_id: str
    server_id: str
    name: str
    cron: str
    status: str
    next_run_time: str | None = None
    scheduled_time: str  # Human readable time like "06:15"


class RestartScheduleRequest(BaseModel):
    """Request model for creating/updating restart schedule."""

    custom_cron: str | None = (
        None  # Optional custom cron, if not provided, use auto-scheduled time
    )


@router.post("/{server_id}/restart-schedule", response_model=RestartScheduleResponse)
async def create_or_update_restart_schedule(
    server_id: str,
    request: RestartScheduleRequest = RestartScheduleRequest(),
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Create or update a restart schedule for a server.

    - If a restart schedule already exists, it will be updated and resumed
    - If no schedule exists, a new one will be created
    - If custom_cron is not provided, uses the automatic conflict-free time slot finder
    """
    # Generate restart schedule name
    schedule_name = f"restart-{server_id}"

    # Initialize restart scheduler
    restart_scheduler = RestartScheduler(cron_manager)

    try:
        # Determine cron expression
        if request.custom_cron:
            cron_expr = request.custom_cron
            # Parse time from cron for display
            cron_parts = cron_expr.strip().split()
            if len(cron_parts) >= 2:
                minute, hour = cron_parts[0], cron_parts[1]
                scheduled_time = f"{hour}:{minute.zfill(2)}"
            else:
                scheduled_time = "Custom"
        else:
            # Use automatic scheduling to avoid conflicts
            cron_expr = await restart_scheduler.generate_restart_cron(
                exclude_server_id=server_id
            )
            hour, minute = await restart_scheduler.find_next_available_restart_time(
                exclude_server_id=server_id
            )
            scheduled_time = f"{hour:02d}:{minute:02d}"

        # Create server restart parameters
        params = ServerRestartParams(server_id=server_id)

        # Check if restart schedule already exists
        existing_jobs = await cron_manager.get_all_cronjobs(
            identifier="restart_server", name=schedule_name
        )

        if existing_jobs:
            # Update existing schedule
            existing_job = existing_jobs[0]
            cronjob_id = existing_job.cronjob_id

            # Update the cron job configuration
            await cron_manager.update_cronjob(
                cronjob_id=cronjob_id,
                identifier="restart_server",
                params=params,
                cron=cron_expr,
            )

            # Resume if it's not active
            if existing_job.status != CronJobStatus.ACTIVE:
                await cron_manager.resume_cronjob(cronjob_id)
        else:
            # Create new restart schedule
            cronjob_id = await cron_manager.create_cronjob(
                identifier="restart_server",
                params=params,
                cron=cron_expr,
                name=schedule_name,
            )

        # Get the updated job config to return current status
        job_config = await cron_manager.get_cronjob_config(cronjob_id)
        if not job_config:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created/updated restart schedule",
            )

        # Get next run time if job is active
        next_run_time = None
        if job_config.status == CronJobStatus.ACTIVE:
            try:
                next_run_datetime = await cron_manager.get_next_run_time(cronjob_id)
                next_run_time = (
                    next_run_datetime.strftime("%Y-%m-%d %H:%M:%S")
                    if next_run_datetime
                    else None
                )
            except ValueError:
                # Job might not be active yet
                pass

        return RestartScheduleResponse(
            cronjob_id=cronjob_id,
            server_id=server_id,
            name=schedule_name,
            cron=cron_expr,
            status=job_config.status.value,
            next_run_time=next_run_time,
            scheduled_time=scheduled_time,
        )

    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create/update restart schedule: {str(e)}",
        )


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

    try:
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

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get restart schedule: {str(e)}",
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

    try:
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

        return {
            "message": f"Restart schedule for server '{server_id}' has been deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete restart schedule: {str(e)}",
        )


@router.post("/{server_id}/restart-schedule/pause")
async def pause_restart_schedule(
    server_id: str,
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Pause the restart schedule for a server.
    """
    schedule_name = f"restart-{server_id}"

    try:
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

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause restart schedule: {str(e)}",
        )


@router.post("/{server_id}/restart-schedule/resume")
async def resume_restart_schedule(
    server_id: str,
    current_user: UserPublic = Depends(get_current_user),
):
    """
    Resume the restart schedule for a server.
    """
    schedule_name = f"restart-{server_id}"

    try:
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

        return {
            "message": f"Restart schedule for server '{server_id}' has been resumed"
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume restart schedule: {str(e)}",
        )
