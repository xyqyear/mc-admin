"""Template migration API router for converting between template and direct modes."""


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserPublic
from app.configuration.api_models import (
    CheckConversionRequest,
    CheckConversionResponse,
    ConvertToDirectRequest,
    ConvertToDirectResponse,
    ConvertToTemplateRequest,
    ConvertToTemplateResponse,
    ExtractVariablesRequest,
    ExtractVariablesResponse,
)

from ...background_tasks import TaskType, get_task_manager
from ...configuration.application import (
    check_rebuild_available,
    convert_without_rebuild,
    rebuild_server_task,
)
from ...configuration.preparation import (
    capture_template_snapshot,
    prepare_template_configuration,
)
from ...configuration.state import read_configuration_state
from ...db.database import get_db
from ...dependencies import get_current_user
from ...logger import get_logger
from ...minecraft import get_docker_mc_manager
from ...servers import get_active_server_by_id
from ...templates import (
    are_yaml_semantically_equal,
    deserialize_variable_definitions_json,
    get_template_by_id,
)
from ...templates.manager import TemplateManager
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["server-template-migration"],
    dependencies=[Depends(admit_server_write)],
)


@router.post(
    "/{server_id}/convert-to-direct",
    response_model=ConvertToDirectResponse,
)
async def convert_to_direct_mode(
    server_id: str,
    request: ConvertToDirectRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Convert a template-based server to direct editing mode.

    This clears the template_id, template_snapshot_json, and variable_values_json
    fields, allowing the user to directly edit the compose file.
    """
    logger = get_logger()
    server = await get_active_server_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    if not server.template_id:
        raise HTTPException(status_code=400, detail="该服务器已经是直接编辑模式")

    await convert_without_rebuild(server_id, None, expected_version=request.expected_version if request else None, actor_id=_.id)

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
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    current = await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)
    current_compose = current.yaml_content

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
        version=current.version,
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

    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    # Check if rendered YAML is semantically identical to current compose
    current = await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)
    current_compose = current.yaml_content
    is_same = are_yaml_semantically_equal(current_compose, configuration.yaml_content)

    return CheckConversionResponse(requires_rebuild=not is_same, version=current.version)


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
    logger = get_logger()
    server = await get_active_server_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    current = await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)
    current.check_version(request.expected_version)

    # Get the template
    template = await get_template_by_id(db, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    try:
        configuration = prepare_template_configuration(
            capture_template_snapshot(template), request.variable_values, expected_version=request.expected_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    if await convert_without_rebuild(server_id, configuration, expected_version=request.expected_version, actor_id=_.id):

        logger.info(
            f"Server {server_id} converted to template mode (no rebuild needed)"
        )
        return ConvertToTemplateResponse(task_id=None, skipped_rebuild=True)

    check_rebuild_available(server_id)
    task_result = await get_task_manager().submit_durable(
        task_type=TaskType.SERVER_REBUILD,
        name=f"重建 {server_id}",
        task_generator=rebuild_server_task(server_id, configuration),
        server_id=server_id,
        cancellable=False,
        actor_id=_.id,
        configuration_version=configuration.fingerprint,
    )

    return ConvertToTemplateResponse(task_id=task_result.task_id, skipped_rebuild=False)
