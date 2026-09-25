"""Template configuration API router for editing template-created servers."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserPublic
from app.configuration.api_models import (
    TemplateConfigPreviewResponse,
    TemplateConfigResponse,
    TemplateConfigUpdateRequest,
    TemplateConfigUpdateResponse,
)

from ...background_tasks import TaskType, get_task_manager
from ...configuration.application import check_rebuild_available, rebuild_server_task
from ...configuration.preparation import prepare_snapshot_configuration
from ...configuration.state import read_configuration_state
from ...db.database import get_db
from ...dependencies import get_current_user
from ...minecraft import get_docker_mc_manager
from ...servers import get_active_server_by_id
from ...templates import (
    TemplatePreviewResponse,
    TemplateSnapshot,
    get_template_by_id,
)
from ...templates.manager import TemplateManager
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["server-template-config"],
    dependencies=[Depends(admit_server_write)],
)


@router.get("/{server_id}/template-config", response_model=TemplateConfigResponse)
async def get_template_config(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get template configuration for a template-created server."""
    # Get server record
    server = await get_active_server_by_id(db, server_id)

    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    if not server.template_id or not server.template_snapshot_json:
        raise HTTPException(status_code=400, detail="该服务器不是使用模板创建的")

    # Parse template snapshot
    snapshot = TemplateSnapshot.model_validate_json(server.template_snapshot_json)
    variable_values = json.loads(server.variable_values_json or "{}")

    # Generate JSON Schema
    json_schema = TemplateManager.generate_json_schema(snapshot.variable_definitions)

    # Check if live template has been updated since snapshot
    has_template_update = False
    template_deleted = False

    live_template = await get_template_by_id(db, snapshot.template_id)

    if live_template is None:
        template_deleted = True
    else:
        snapshot_time = snapshot.source_updated_at or datetime.fromisoformat(snapshot.snapshot_time)
        if live_template.updated_at > snapshot_time:
            has_template_update = True

    return TemplateConfigResponse(
        version=(await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)).version,
        server_id=server_id,
        template_id=snapshot.template_id,
        template_name=snapshot.template_name,
        yaml_template=snapshot.yaml_template,
        variable_definitions=snapshot.variable_definitions,
        variable_values=variable_values,
        json_schema=json_schema,
        snapshot_time=snapshot.snapshot_time,
        has_template_update=has_template_update,
        template_deleted=template_deleted,
    )


@router.put("/{server_id}/template-config", response_model=TemplateConfigUpdateResponse)
async def update_template_config(
    server_id: str,
    request: TemplateConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Update template configuration for a template-created server.

    This will re-render the YAML template with new variable values
    and rebuild the server with the new compose file.

    Returns a task_id for tracking the rebuild progress.
    """
    # Get server record
    server = await get_active_server_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    current = await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)
    current.check_version(request.expected_version)
    try:
        configuration = prepare_snapshot_configuration(server, request.variable_values, expected_version=request.expected_version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    instance = get_docker_mc_manager().get_instance(server_id)

    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

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

    return TemplateConfigUpdateResponse(task_id=task_result.task_id)


@router.get(
    "/{server_id}/template-config/preview", response_model=TemplateConfigPreviewResponse
)
async def preview_template_config(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Check if a server was created with a template."""
    server = await get_active_server_by_id(db, server_id)

    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    return TemplateConfigPreviewResponse(
        is_template_based=bool(server.template_id),
        template_id=server.template_id,
    )


@router.post(
    "/{server_id}/template-config/preview", response_model=TemplatePreviewResponse
)
async def preview_rendered_template_config(
    server_id: str,
    request: TemplateConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    server = await get_active_server_by_id(db, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="服务器不存在")
    try:
        configuration = prepare_snapshot_configuration(server, request.variable_values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TemplatePreviewResponse(rendered_yaml=configuration.yaml_content)
