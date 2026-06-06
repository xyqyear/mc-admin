"""
Cron job management API endpoints.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel

from ..cron import cron_manager, cron_registry
from ..dependencies import get_current_user
from ..models import CronJobStatus, UserPublic

router = APIRouter(prefix="/cron", tags=["cron"])


def _cron_value_error_status(error: ValueError) -> int:
    message = str(error).lower()
    if "not found" in message or "不存在" in message:
        return http_status.HTTP_404_NOT_FOUND
    if (
        "cannot" in message
        or "already" in message
        or "not active" in message
        or "不能" in message
        or "已" in message
        or "未处于运行中" in message
    ):
        return http_status.HTTP_409_CONFLICT
    return http_status.HTTP_400_BAD_REQUEST


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
    name: Optional[str] = None
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
    is_system: bool
    status: str
    created_at: datetime
    updated_at: datetime


class CronJobExecutionResponse(BaseModel):
    """Response model for cron job execution information."""

    execution_id: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_ms: Optional[int]
    status: str
    messages: List[str]


class CronJobNextRunTimeResponse(BaseModel):
    """Response model for cron job next run time."""

    cronjob_id: str
    next_run_time: datetime


class RegisteredCronJobResponse(BaseModel):
    """Response model for registered cron job information."""

    identifier: str
    description: str
    parameter_schema: dict
    is_system: bool
    default_cron: Optional[str] = None
    default_second: Optional[str] = None
    default_params: Optional[dict] = None
    default_name: Optional[str] = None


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
                is_system=registration.is_system,
                default_cron=registration.default_cron,
                default_second=registration.default_second,
                default_params=(
                    registration.default_params.model_dump()
                    if registration.default_params
                    else None
                ),
                default_name=registration.default_name,
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
    # Pass filters directly to manager
    cronjob_configs = await cron_manager.get_all_cronjobs(
        identifier=identifier, status=status
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
                is_system=config.is_system,
                status=config.status.value,
                created_at=config.created_at,
                updated_at=config.updated_at,
            )
        )

    return result


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
            detail=f"定时任务类型 '{request.identifier}' 未注册",
        )

    # Validate parameters against schema
    try:
        params = schema_cls.model_validate(request.params)
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"任务参数无效: {str(e)}",
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
        return {"cronjob_id": cronjob_id, "message": "定时任务创建成功"}
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建定时任务失败: {str(e)}",
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
            status_code=http_status.HTTP_404_NOT_FOUND, detail="定时任务不存在"
        )

    return CronJobResponse(
        cronjob_id=cronjob_config.cronjob_id,
        identifier=cronjob_config.identifier,
        name=cronjob_config.name,
        cron=cronjob_config.cron,
        second=cronjob_config.second,
        params=cronjob_config.params.model_dump(),
        execution_count=cronjob_config.execution_count,
        is_system=cronjob_config.is_system,
        status=cronjob_config.status.value,
        created_at=cronjob_config.created_at,
        updated_at=cronjob_config.updated_at,
    )


@router.put("/{cronjob_id}", response_model=dict)
async def update_cronjob(
    cronjob_id: str,
    request: UpdateCronJobRequest,
    _: UserPublic = Depends(get_current_user),
):
    """
    Update an existing cron job configuration.

    Updates the configuration of an existing cron job.
    """
    # Validate that the identifier is registered
    schema_cls = cron_registry.get_schema_class(request.identifier)
    if not schema_cls:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"定时任务类型 '{request.identifier}' 未注册",
        )

    # Validate parameters against schema
    try:
        params = schema_cls.model_validate(request.params)
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"任务参数无效: {str(e)}",
        )

    # Update the cron job
    try:
        await cron_manager.update_cronjob(
            cronjob_id=cronjob_id,
            identifier=request.identifier,
            params=params,
            cron=request.cron,
            name=request.name,
            second=request.second,
        )
        return {"message": "定时任务更新成功"}
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新定时任务失败: {str(e)}",
        )


@router.post("/{cronjob_id}/pause")
async def pause_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Pause a cron job.

    Pauses execution of a cron job until it is resumed.
    """
    try:
        await cron_manager.pause_cronjob(cronjob_id)
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=str(e),
        )
    return {"message": "定时任务已暂停"}


@router.post("/{cronjob_id}/resume")
async def resume_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Resume a paused cron job.

    Resumes execution of a previously paused cron job.
    """
    try:
        await cron_manager.resume_cronjob(cronjob_id)
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=str(e),
        )
    return {"message": "定时任务已恢复"}


@router.delete("/{cronjob_id}")
async def cancel_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Cancel a cron job.

    Cancels (soft deletes) a cron job. The cron job configuration and execution
    history are preserved but the cron job will no longer execute.
    """
    try:
        await cron_manager.cancel_cronjob(cronjob_id)
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=str(e),
        )
    return {"message": "定时任务已取消"}


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
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=str(e),
        )

    return [
        CronJobExecutionResponse(
            execution_id=ex.execution_id,
            started_at=ex.started_at,
            ended_at=ex.ended_at,
            duration_ms=ex.duration_ms,
            status=ex.status.value if hasattr(ex.status, "value") else ex.status,
            messages=ex.messages,
        )
        for ex in executions
    ]


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
        raise HTTPException(status_code=_cron_value_error_status(e), detail=str(e))

    if next_run_time is None:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="无法计算下次运行时间",
        )

    return CronJobNextRunTimeResponse(
        cronjob_id=cronjob_id, next_run_time=next_run_time
    )
