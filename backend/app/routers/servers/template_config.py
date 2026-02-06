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
from ...templates import (
    VariableDefinition,
    cast_variables_json,
)
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
    variables: list[VariableDefinition]
    variable_values: dict[str, Any]
    json_schema: dict
    snapshot_time: str


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
    template_snapshot = json.loads(server.template_snapshot_json)
    variable_values = json.loads(server.variable_values_json or "{}")

    # Parse user variables from snapshot
    user_variables = cast_variables_json(json.dumps(template_snapshot["variables"]))

    # Generate JSON Schema
    json_schema = TemplateManager.generate_json_schema(user_variables)

    return TemplateConfigResponse(
        server_id=server_id,
        template_id=template_snapshot["template_id"],
        template_name=template_snapshot["template_name"],
        yaml_template=template_snapshot["yaml_template"],
        variables=user_variables,
        variable_values=variable_values,
        json_schema=json_schema,
        snapshot_time=template_snapshot["snapshot_time"],
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
    template_snapshot = json.loads(server.template_snapshot_json)
    user_variables = cast_variables_json(json.dumps(template_snapshot["variables"]))

    # Validate variable values
    errors = TemplateManager.validate_variable_values(
        user_variables, request.variable_values
    )
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    # Render YAML
    try:
        rendered_yaml = TemplateManager.render_yaml(
            template_snapshot["yaml_template"], request.variable_values
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
