"""Template migration API router for converting between template and direct modes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...background_tasks import TaskType, task_manager
from ...db.database import get_db
from ...dependencies import get_current_user
from ...logger import logger
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...servers import get_active_server_by_id, rebuild_server_task
from ...servers.configuration import (
    capture_template_snapshot,
    clear_template_configuration,
    prepare_template_configuration,
    save_configuration_metadata,
)
from ...templates import (
    VariableDefinition,
    are_yaml_semantically_equal,
    deserialize_variable_definitions_json,
    get_template_by_id,
)
from ...templates.manager import TemplateManager

router = APIRouter(
    prefix="/servers",
    tags=["server-template-migration"],
)


class ConvertToDirectResponse(BaseModel):
    """Response model for converting to direct mode."""

    success: bool


class ExtractVariablesRequest(BaseModel):
    """Request model for extracting variables."""

    template_id: int


class ExtractVariablesResponse(BaseModel):
    """Response model for extracted variables."""

    extracted_values: dict[str, Any]
    warnings: list[str]
    json_schema: dict
    variable_definitions: list[VariableDefinition]
    current_compose: str
    rendered_compose: str


class ConvertToTemplateRequest(BaseModel):
    """Request model for converting to template mode."""

    template_id: int
    variable_values: dict[str, Any]


class ConvertToTemplateResponse(BaseModel):
    """Response model for converting to template mode."""

    task_id: str | None = None
    skipped_rebuild: bool = False


class CheckConversionRequest(BaseModel):
    """Request model for checking if conversion requires rebuild."""

    template_id: int
    variable_values: dict[str, Any]


class CheckConversionResponse(BaseModel):
    """Response model for conversion rebuild check."""

    requires_rebuild: bool


@router.post(
    "/{server_id}/convert-to-direct",
    response_model=ConvertToDirectResponse,
)
async def convert_to_direct_mode(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Convert a template-based server to direct editing mode.

    This clears the template_id, template_snapshot_json, and variable_values_json
    fields, allowing the user to directly edit the compose file.
    """
    server = await get_active_server_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    if not server.template_id:
        raise HTTPException(status_code=400, detail="该服务器已经是直接编辑模式")

    await clear_template_configuration(db, server)

    logger.info(f"Server {server_id} converted to direct editing mode")
    return ConvertToDirectResponse(success=True)


@router.post(
    "/{server_id}/extract-variables",
    response_model=ExtractVariablesResponse,
)
async def extract_variables(
    server_id: str,
    request: ExtractVariablesRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Extract variable values from current compose file using a template.

    This is used when converting from direct mode to template mode.
    Returns extracted values, warnings, and a preview of the rendered compose.
    """
    server = await get_active_server_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # Get the template
    template = await get_template_by_id(db, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    # Get current compose content
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    current_compose = await instance.get_compose_file()

    # Parse variable definitions
    variable_definitions = deserialize_variable_definitions_json(
        template.variable_definitions_json
    )

    # Extract variables from compose
    extracted_values, warnings = TemplateManager.extract_variables_from_compose(
        template.yaml_template,
        current_compose,
        variable_definitions,
    )

    # Generate JSON schema
    json_schema = TemplateManager.generate_json_schema(variable_definitions)

    # Render compose with extracted values for preview
    try:
        rendered_compose = TemplateManager.render_yaml(
            template.yaml_template, extracted_values
        )
    except ValueError as e:
        rendered_compose = f"# 渲染失败: {e}\n# 请调整变量值后重试"

    return ExtractVariablesResponse(
        extracted_values=extracted_values,
        warnings=warnings,
        json_schema=json_schema,
        variable_definitions=variable_definitions,
        current_compose=current_compose,
        rendered_compose=rendered_compose,
    )


@router.post(
    "/{server_id}/check-conversion",
    response_model=CheckConversionResponse,
)
async def check_conversion(
    server_id: str,
    request: CheckConversionRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Check if converting to template mode requires a rebuild.

    Compares the rendered template YAML with the current compose file
    to determine if they are semantically identical.
    """
    server = await get_active_server_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # Get the template
    template = await get_template_by_id(db, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    try:
        configuration = prepare_template_configuration(
            capture_template_snapshot(template), request.variable_values
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    # Check if rendered YAML is semantically identical to current compose
    current_compose = await instance.get_compose_file()
    is_same = are_yaml_semantically_equal(current_compose, configuration.yaml_content)

    return CheckConversionResponse(requires_rebuild=not is_same)


@router.post(
    "/{server_id}/convert-to-template",
    response_model=ConvertToTemplateResponse,
)
async def convert_to_template_mode(
    server_id: str,
    request: ConvertToTemplateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Convert a direct-mode server to template mode.

    This validates the variable values, renders the YAML, creates a template
    snapshot, and rebuilds the server with the new compose file.
    """
    server = await get_active_server_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # Get the template
    template = await get_template_by_id(db, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    try:
        configuration = prepare_template_configuration(
            capture_template_snapshot(template), request.variable_values
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    # Check if rendered YAML is semantically identical to current compose
    current_compose = await instance.get_compose_file()
    is_same = are_yaml_semantically_equal(current_compose, configuration.yaml_content)

    if is_same:
        await save_configuration_metadata(db, server_id, configuration)

        logger.info(
            f"Server {server_id} converted to template mode (no rebuild needed)"
        )
        return ConvertToTemplateResponse(task_id=None, skipped_rebuild=True)

    # Submit rebuild task
    task_result = task_manager.submit(
        task_type=TaskType.SERVER_REBUILD,
        name=f"重建 {server_id}",
        task_generator=rebuild_server_task(server_id, configuration),
        server_id=server_id,
        cancellable=False,
    )

    return ConvertToTemplateResponse(task_id=task_result.task_id, skipped_rebuild=False)
