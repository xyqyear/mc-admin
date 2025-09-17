"""
Cron job management API endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel

from ..cron import cron_manager, cron_registry
from ..dependencies import get_current_user
from ..models import CronJobStatus, UserPublic

router = APIRouter(prefix="/cron", tags=["cron"])


class CreateCronJobRequest(BaseModel):
    """Request model for creating a cron job."""

    identifier: str
    params: dict  # Will be validated against the schema class
    cron: str
    cronjob_id: Optional[str] = None
    name: Optional[str] = None
    second: Optional[str] = None


class UpdateCronJobRequest(BaseModel):
    """Request model for updating a cron job."""

    identifier: str
    params: dict  # Will be validated against the schema class
    cron: str
    second: Optional[str] = None


class CronJobResponse(BaseModel):
    """Response model for cron job information."""

    cronjob_id: str
    identifier: str
    name: str
    cron: str
    second: Optional[str] = None
    params: dict
    execution_count: int
    status: str
    created_at: str
    updated_at: str


class CronJobExecutionResponse(BaseModel):
    """Response model for cron job execution information."""

    execution_id: str
    started_at: Optional[str]
    ended_at: Optional[str]
    duration_ms: Optional[int]
    status: str
    messages: List[str]


class CronJobNextRunTimeResponse(BaseModel):
    """Response model for cron job next run time."""

    cronjob_id: str
    next_run_time: str


class RegisteredCronJobResponse(BaseModel):
    """Response model for registered cron job information."""

    identifier: str
    description: str
    parameter_schema: dict


@router.get("/registered", response_model=List[RegisteredCronJobResponse])
async def list_registered_cronjobs(_: UserPublic = Depends(get_current_user)):
    """
    List all registered cron job types.

    Returns information about all available cron job types that can be scheduled.
    """
    registered_cronjobs = cron_registry.get_all_cronjobs()

    result = []
    for identifier, registration in registered_cronjobs.items():
        result.append(
            RegisteredCronJobResponse(
                identifier=identifier,
                description=registration.description,
                parameter_schema=registration.schema_cls.model_json_schema(),
            )
        )

    return result


@router.get("/", response_model=List[CronJobResponse])
async def list_cronjobs(
    identifier: Optional[str] = Query(
        None, description="Filter by job type identifier"
    ),
    status: List[CronJobStatus] = Query(
        default=[CronJobStatus.ACTIVE, CronJobStatus.PAUSED],
        description="Filter by job status (default: active and paused jobs)",
    ),
    _: UserPublic = Depends(get_current_user),
):
    """
    List cron jobs with optional filtering.

    Returns information about cron jobs in the system, optionally filtered by
    job type identifier and/or status.

    Args:
        identifier: Optional job type identifier to filter by
        status: List of job statuses to include (default: [active, paused])
    """
    try:
        # Pass filters directly to manager
        cronjob_configs = await cron_manager.get_all_cronjobs(
            identifier=identifier,
            status=status
        )

        result = []
        for config in cronjob_configs:
            result.append(
                CronJobResponse(
                    cronjob_id=config.cronjob_id,
                    identifier=config.identifier,
                    name=config.name,
                    cron=config.cron,
                    second=config.second,
                    params=config.params.model_dump(),
                    execution_count=config.execution_count,
                    status=config.status.value,
                    created_at=config.created_at.isoformat(),
                    updated_at=config.updated_at.isoformat(),
                )
            )

        return result
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list cron jobs: {str(e)}",
        )


@router.post("/", response_model=dict)
async def create_cronjob(
    request: CreateCronJobRequest, _: UserPublic = Depends(get_current_user)
):
    """
    Create a new cron job.

    Creates a new scheduled cron job with the specified parameters.
    """
    # Validate that the identifier is registered
    schema_cls = cron_registry.get_schema_class(request.identifier)
    if not schema_cls:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"CronJob identifier '{request.identifier}' is not registered",
        )

    # Validate parameters against schema
    try:
        params = schema_cls.model_validate(request.params)
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameters: {str(e)}",
        )

    # Create the cron job
    try:
        cronjob_id = await cron_manager.create_cronjob(
            identifier=request.identifier,
            params=params,
            cron=request.cron,
            cronjob_id=request.cronjob_id,
            name=request.name,
            second=request.second,
        )
        return {"cronjob_id": cronjob_id, "message": "CronJob created successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create cron job: {str(e)}",
        )


@router.get("/{cronjob_id}", response_model=CronJobResponse)
async def get_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Get cron job configuration and status.

    Returns detailed information about a specific cron job.
    """
    cronjob_config = await cron_manager.get_cronjob_config(cronjob_id)
    if not cronjob_config:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="CronJob not found"
        )

    return CronJobResponse(
        cronjob_id=cronjob_config.cronjob_id,
        identifier=cronjob_config.identifier,
        name=cronjob_config.name,
        cron=cronjob_config.cron,
        second=cronjob_config.second,
        params=cronjob_config.params.model_dump(),
        execution_count=cronjob_config.execution_count,
        status=cronjob_config.status.value,
        created_at=cronjob_config.created_at.isoformat(),
        updated_at=cronjob_config.updated_at.isoformat(),
    )


@router.put("/{cronjob_id}", response_model=dict)
async def update_cronjob(
    cronjob_id: str,
    request: UpdateCronJobRequest,
    _: UserPublic = Depends(get_current_user)
):
    """
    Update an existing cron job configuration.

    Updates the configuration of an existing cron job. The task name cannot be changed.
    """
    # Validate that the identifier is registered
    schema_cls = cron_registry.get_schema_class(request.identifier)
    if not schema_cls:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"CronJob identifier '{request.identifier}' is not registered",
        )

    # Validate parameters against schema
    try:
        params = schema_cls.model_validate(request.params)
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameters: {str(e)}",
        )

    # Update the cron job
    try:
        await cron_manager.update_cronjob(
            cronjob_id=cronjob_id,
            identifier=request.identifier,
            params=params,
            cron=request.cron,
            second=request.second,
        )
        return {"message": "CronJob updated successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update cron job: {str(e)}",
        )


@router.post("/{cronjob_id}/pause")
async def pause_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Pause a cron job.

    Pauses execution of a cron job until it is resumed.
    """
    try:
        await cron_manager.pause_cronjob(cronjob_id)
        return {"message": "CronJob paused successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause cron job: {str(e)}",
        )


@router.post("/{cronjob_id}/resume")
async def resume_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Resume a paused cron job.

    Resumes execution of a previously paused cron job.
    """
    try:
        await cron_manager.resume_cronjob(cronjob_id)
        return {"message": "CronJob resumed successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume cron job: {str(e)}",
        )


@router.delete("/{cronjob_id}")
async def cancel_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Cancel a cron job.

    Cancels (soft deletes) a cron job. The cron job configuration and execution
    history are preserved but the cron job will no longer execute.
    """
    try:
        await cron_manager.cancel_cronjob(cronjob_id)
        return {"message": "CronJob cancelled successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel cron job: {str(e)}",
        )


@router.get("/{cronjob_id}/executions", response_model=List[CronJobExecutionResponse])
async def get_cronjob_executions(
    cronjob_id: str, limit: int = 50, _: UserPublic = Depends(get_current_user)
):
    """
    Get cron job execution history.

    Returns the execution history for a specific cron job.
    """
    try:
        executions = await cron_manager.get_execution_history(cronjob_id, limit)

        return [
            CronJobExecutionResponse(
                execution_id=ex.execution_id,
                started_at=ex.started_at.isoformat() if ex.started_at else None,
                ended_at=ex.ended_at.isoformat() if ex.ended_at else None,
                duration_ms=ex.duration_ms,
                status=ex.status.value if hasattr(ex.status, "value") else ex.status,
                messages=ex.messages,
            )
            for ex in executions
        ]
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cron job executions: {str(e)}",
        )


@router.get("/{cronjob_id}/next-run-time", response_model=CronJobNextRunTimeResponse)
async def get_cronjob_next_run_time(
    cronjob_id: str, _: UserPublic = Depends(get_current_user)
):
    """
    Get the next scheduled run time for a cron job.

    Returns the next run time for an active cron job. Only active cron jobs
    have scheduled run times.
    """
    try:
        next_run_time = await cron_manager.get_next_run_time(cronjob_id)
    except ValueError as e:
        # Handle cases where job not found or not active
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get next run time: {str(e)}",
        )
    if next_run_time is None:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to determine next run time",
        )

    return CronJobNextRunTimeResponse(
        cronjob_id=cronjob_id, next_run_time=next_run_time.isoformat()
    )
