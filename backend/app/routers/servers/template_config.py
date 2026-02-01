"""Template configuration API router for editing template-created servers."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...minecraft import docker_mc_manager
from ...models import Server, ServerStatus, UserPublic
from ...templates.manager import TemplateManager
from ...templates.models import SYSTEM_RESERVED_VARIABLES, VariableDefinition

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
    system_variables: list[VariableDefinition]
    variable_values: dict[str, Any]
    json_schema: dict
    snapshot_time: str


class TemplateConfigUpdateRequest(BaseModel):
    """Request model for updating template configuration."""

    variable_values: dict[str, Any]


class TemplateConfigUpdateResponse(BaseModel):
    """Response model for template configuration update."""

    message: str
    rendered_yaml: str


def _parse_variables_json(variables_json: str) -> list[VariableDefinition]:
    """Parse variables JSON string to list of VariableDefinition."""
    raw_list = json.loads(variables_json)
    adapter = TypeAdapter(list[VariableDefinition])
    return adapter.validate_python(raw_list)


@router.get("/{server_id}/template-config", response_model=TemplateConfigResponse)
async def get_template_config(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get template configuration for a template-created server."""
    # Get server record
    result = await db.execute(
        select(Server).where(
            Server.server_id == server_id, Server.status == ServerStatus.ACTIVE
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    if not server.template_id or not server.template_snapshot_json:
        raise HTTPException(status_code=400, detail="该服务器不是使用模板创建的")

    # Parse template snapshot
    template_snapshot = json.loads(server.template_snapshot_json)
    variable_values = json.loads(server.variable_values_json or "{}")

    # Parse user variables from snapshot
    user_variables = _parse_variables_json(json.dumps(template_snapshot["variables"]))

    # Generate JSON Schema
    json_schema = TemplateManager.generate_json_schema(user_variables)

    return TemplateConfigResponse(
        server_id=server_id,
        template_id=template_snapshot["template_id"],
        template_name=template_snapshot["template_name"],
        yaml_template=template_snapshot["yaml_template"],
        variables=user_variables,
        system_variables=[v.model_dump() for v in SYSTEM_RESERVED_VARIABLES],
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
    and update the server's compose file.
    """
    # Get server record
    result = await db.execute(
        select(Server).where(
            Server.server_id == server_id, Server.status == ServerStatus.ACTIVE
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    if not server.template_id or not server.template_snapshot_json:
        raise HTTPException(status_code=400, detail="该服务器不是使用模板创建的")

    # Parse template snapshot
    template_snapshot = json.loads(server.template_snapshot_json)
    user_variables = _parse_variables_json(json.dumps(template_snapshot["variables"]))

    # Validate variable values
    errors = TemplateManager.validate_variable_values(
        user_variables, request.variable_values
    )
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Render YAML
    try:
        rendered_yaml = TemplateManager.render_yaml(
            template_snapshot["yaml_template"], request.variable_values
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Get instance and update compose file
    instance = docker_mc_manager.get_instance(server_id)

    if not await instance.exists():
        raise HTTPException(status_code=404, detail="服务器目录不存在")

    # Update compose file
    await instance.update_compose_file(rendered_yaml)

    # Update server record with new variable values
    server.variable_values_json = json.dumps(request.variable_values)
    server.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return TemplateConfigUpdateResponse(
        message="模板配置更新成功",
        rendered_yaml=rendered_yaml,
    )


@router.get("/{server_id}/template-config/preview")
async def preview_template_config(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Check if a server was created with a template."""
    # Get server record
    result = await db.execute(
        select(Server).where(
            Server.server_id == server_id, Server.status == ServerStatus.ACTIVE
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    return {
        "is_template_based": bool(
            server.template_id and server.template_snapshot_json
        ),
        "template_id": server.template_id,
    }
