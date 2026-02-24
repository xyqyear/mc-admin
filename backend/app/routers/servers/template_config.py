"""Template configuration API router for editing template-created servers."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...background_tasks import TaskType, task_manager
from ...db.database import get_async_session, get_db
from ...dependencies import get_current_user
from ...logger import logger
from ...minecraft import docker_mc_manager
from ...models import UserPublic
from ...servers import get_active_server_by_id, rebuild_server_task
from ...templates import TemplateSnapshot, VariableDefinition, get_template_by_id
from ...templates.manager import TemplateManager

router = APIRouter(
    prefix="/servers",
    tags=["server-template-config"],
)


class TemplateConfigResponse(BaseModel):
    """Response model for template configuration."""

    server_id: str
    template_id: int
    template_name: str
    yaml_template: str
    variable_definitions: list[VariableDefinition]
    variable_values: dict[str, Any]
    json_schema: dict
    snapshot_time: str
    has_template_update: bool = False
    template_deleted: bool = False


class TemplateConfigUpdateRequest(BaseModel):
    """Request model for updating template configuration."""

    variable_values: dict[str, Any]


class TemplateConfigUpdateResponse(BaseModel):
    """Response model for template configuration update."""

    task_id: str


class TemplateConfigPreviewResponse(BaseModel):
    """Response model for template configuration preview."""

    is_template_based: bool
    template_id: int | None


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

    # Generate JSON Schema (only for variables actually used in YAML)
    yaml_variables = TemplateManager.filter_yaml_variables(
        snapshot.yaml_template, snapshot.variable_definitions
    )
    json_schema = TemplateManager.generate_json_schema(yaml_variables)

    # Check if live template has been updated since snapshot
    has_template_update = False
    template_deleted = False

    live_template = await get_template_by_id(db, snapshot.template_id)

    if live_template is None:
        template_deleted = True
    else:
        snapshot_time = datetime.fromisoformat(snapshot.snapshot_time)
        if live_template.updated_at > snapshot_time:
            has_template_update = True

    return TemplateConfigResponse(
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

    if not server.template_id or not server.template_snapshot_json:
        raise HTTPException(status_code=400, detail="该服务器不是使用模板创建的")

    # Parse template snapshot
    snapshot = TemplateSnapshot.model_validate_json(server.template_snapshot_json)

    # Validate variable values (only for variables actually used in YAML)
    yaml_variables = TemplateManager.filter_yaml_variables(
        snapshot.yaml_template, snapshot.variable_definitions
    )
    errors = TemplateManager.validate_variable_values(
        yaml_variables, request.variable_values
    )
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    # Render YAML
    try:
        rendered_yaml = TemplateManager.render_yaml(
            snapshot.yaml_template, request.variable_values
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    instance = docker_mc_manager.get_instance(server_id)

    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    task_result = task_manager.submit(
        task_type=TaskType.SERVER_REBUILD,
        name=f"重建 {server_id}",
        task_generator=rebuild_server_task(server_id, rendered_yaml),
        server_id=server_id,
        cancellable=False,
    )

    # update the variable values in the database after task succeeds
    async def update_variable_values_after_rebuild():
        result = await task_result.awaitable
        print(result)
        if not result.success:
            return
        async with get_async_session() as session:
            server = await get_active_server_by_id(session, server_id)
            if not server:
                logger.error(
                    f"Failed to update variable values for server {server_id}: server not found"
                )
                return
            server.variable_values_json = json.dumps(request.variable_values)
            server.updated_at = datetime.now(timezone.utc)
            await session.commit()

    asyncio.create_task(update_variable_values_after_rebuild())

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
