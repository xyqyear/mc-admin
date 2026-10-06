"""
Cron job management API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import ValidationError

from app.auth.schemas import UserPublic
from app.cron.models import CronJobStatus

from ..cron import get_cron_manager, get_cron_registry
from ..cron.api_models import (
    CreateCronJobRequest,
    CronJobExecutionResponse,
    CronJobNextRunTimeResponse,
    CronJobResponse,
    RegisteredCronJobResponse,
    UpdateCronJobRequest,
)
from ..cron.bindings import binding_issue_message
from ..cron.errors import cron_error_message
from ..dependencies import get_current_user
from ..dynamic_config.schemas import BaseConfigSchema
from ..errors import log_safe_error
from ..logger import get_logger

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


def _cron_validation_detail(error: Exception, schema: type[BaseConfigSchema]) -> str:
    if not isinstance(error, ValidationError):
        return "任务参数无效"
    diagnostics = []
    messages = {
        "missing": "必填字段缺失", "int_parsing": "应为整数", "int_type": "应为整数",
        "float_parsing": "应为数字", "float_type": "应为数字", "string_type": "应为字符串",
        "bool_parsing": "应为布尔值", "bool_type": "应为布尔值", "list_type": "应为列表",
        "literal_error": "应为允许的选项", "extra_forbidden": "存在不支持的字段",
    }
    bounds = {
        "greater_than": ("exclusiveMinimum", "必须大于"),
        "greater_than_equal": ("minimum", "必须大于或等于"),
        "less_than": ("exclusiveMaximum", "必须小于"),
        "less_than_equal": ("maximum", "必须小于或等于"),
    }
    properties = schema.model_json_schema().get("properties", {})
    for entry in error.errors(include_input=False, include_url=False):
        location = entry["loc"]
        field = (
            location[0]
            if location and isinstance(location[0], str) and location[0] in schema.model_fields
            else "参数"
        )
        field += "".join(f"[{index}]" for index in location[1:] if isinstance(index, int))
        message = messages.get(entry["type"], "字段值无效")
        context = entry.get("ctx", {})
        if entry["type"] in bounds:
            key, label = bounds[entry["type"]]
            bound = properties.get(field, {}).get(key)
            if isinstance(bound, (int, float)):
                message = f"{label} {bound}"
        cause = context.get("error")
        if isinstance(cause, ValueError) and "cron_public_message" in vars(cause):
            message = cron_error_message(cause)
        diagnostics.append(f"{field}: {message}")
    return "任务参数无效: " + "; ".join(diagnostics)


@router.get("/registered", response_model=list[RegisteredCronJobResponse])
async def list_registered_cronjobs(_: UserPublic = Depends(get_current_user)):
    """
    List all registered cron job types.

    Returns information about all available cron job types that can be scheduled.
    """
    registered_cronjobs = get_cron_registry().get_all_cronjobs()

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


@router.get("/", response_model=list[CronJobResponse])
async def list_cronjobs(
    identifier: str | None = Query(
        None, description="Filter by job type identifier"
    ),
    status: list[CronJobStatus] = Query(
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
    cronjob_configs = await get_cron_manager().get_all_cronjobs(
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
                managed_server_generation=config.managed_server_generation,
                managed_purpose=config.managed_purpose,
                managed_binding_issue=binding_issue_message(config.managed_binding_issue) if config.managed_binding_issue else None,
                execution_count=config.execution_count,
                is_system=config.is_system,
                status=config.status.value,
                registration_status=config.registration_status,
                registration_error=config.registration_error,
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
    logger = get_logger()
    # Validate that the identifier is registered
    schema_cls = get_cron_registry().get_schema_class(request.identifier)
    if not schema_cls:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="定时任务类型未注册",
        )

    # Validate parameters against schema
    try:
        params = schema_cls.model_validate(request.params)
    except Exception as e:  # noqa: BLE001 - parameter validation failures retain the HTTP 400 contract
        log_safe_error(e, "Cron parameter validation failed", logger=logger)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=_cron_validation_detail(e, schema_cls),
        )

    # Create the cron job
    try:
        cronjob_id = await get_cron_manager().create_cronjob(
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
            detail=cron_error_message(e),
        )
    except Exception as e:  # noqa: BLE001 - unexpected creation errors retain a safe HTTP 500 response
        log_safe_error(e, "Cron creation failed", logger=logger)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建定时任务失败: {cron_error_message(e)}",
        )


@router.get("/{cronjob_id}", response_model=CronJobResponse)
async def get_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Get cron job configuration and status.

    Returns detailed information about a specific cron job.
    """
    cronjob_config = await get_cron_manager().get_cronjob_config(cronjob_id)
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
        managed_server_generation=cronjob_config.managed_server_generation,
        managed_purpose=cronjob_config.managed_purpose,
        managed_binding_issue=binding_issue_message(cronjob_config.managed_binding_issue) if cronjob_config.managed_binding_issue else None,
        execution_count=cronjob_config.execution_count,
        is_system=cronjob_config.is_system,
        status=cronjob_config.status.value,
        registration_status=cronjob_config.registration_status,
        registration_error=cronjob_config.registration_error,
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
    logger = get_logger()
    # Validate that the identifier is registered
    schema_cls = get_cron_registry().get_schema_class(request.identifier)
    if not schema_cls:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="定时任务类型未注册",
        )

    # Validate parameters against schema
    try:
        params = schema_cls.model_validate(request.params)
    except Exception as e:  # noqa: BLE001 - parameter validation failures retain the HTTP 400 contract
        log_safe_error(e, "Cron parameter validation failed", logger=logger)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=_cron_validation_detail(e, schema_cls),
        )

    # Update the cron job
    try:
        await get_cron_manager().update_cronjob(
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
            detail=cron_error_message(e),
        )
    except Exception as e:  # noqa: BLE001 - unexpected update errors retain a safe HTTP 500 response
        log_safe_error(e, "Cron update failed", logger=logger)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新定时任务失败: {cron_error_message(e)}",
        )


@router.post("/{cronjob_id}/pause")
async def pause_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Pause a cron job.

    Pauses execution of a cron job until it is resumed.
    """
    try:
        await get_cron_manager().pause_cronjob(cronjob_id)
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=cron_error_message(e),
        )
    return {"message": "定时任务已暂停"}


@router.post("/{cronjob_id}/resume")
async def resume_cronjob(cronjob_id: str, _: UserPublic = Depends(get_current_user)):
    """
    Resume a paused cron job.

    Resumes execution of a previously paused cron job.
    """
    try:
        await get_cron_manager().resume_cronjob(cronjob_id)
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=cron_error_message(e),
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
        await get_cron_manager().cancel_cronjob(cronjob_id)
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=cron_error_message(e),
        )
    return {"message": "定时任务已取消"}


@router.get("/{cronjob_id}/executions", response_model=list[CronJobExecutionResponse])
async def get_cronjob_executions(
    cronjob_id: str, limit: int = 50, _: UserPublic = Depends(get_current_user)
):
    """
    Get cron job execution history.

    Returns the execution history for a specific cron job.
    """
    try:
        executions = await get_cron_manager().get_execution_history(cronjob_id, limit)
    except ValueError as e:
        raise HTTPException(
            status_code=_cron_value_error_status(e),
            detail=cron_error_message(e),
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
        next_run_time = await get_cron_manager().get_next_run_time(cronjob_id)
    except ValueError as e:
        raise HTTPException(status_code=_cron_value_error_status(e), detail=cron_error_message(e))

    if next_run_time is None:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="无法计算下次运行时间",
        )

    return CronJobNextRunTimeResponse(
        cronjob_id=cronjob_id, next_run_time=next_run_time
    )
