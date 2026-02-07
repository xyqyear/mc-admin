"""Server creation API router supporting both traditional YAML and template modes."""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...minecraft import docker_mc_manager
from ...models import ServerTemplate, UserPublic
from ...players import player_system_manager
from ...servers import (
    check_port_conflicts,
    create_server_record,
    extract_ports_from_yaml,
)
from ...templates import TemplateSnapshot, deserialize_variable_definitions_json
from ...templates.manager import TemplateManager

router = APIRouter(
    prefix="/servers",
    tags=["server-creation"],
)


class CreateServerRequest(BaseModel):
    """Request model for server creation.

    Supports two modes:
    - Traditional mode: Provide yaml_content directly
    - Template mode: Provide template_id and variable_values
    """

    yaml_content: Optional[str] = None
    template_id: Optional[int] = None
    variable_values: Optional[dict] = None


@router.post("/{server_id}")
async def create_server(
    server_id: str,
    create_request: CreateServerRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Create a new Minecraft server.

    Supports two modes:
    - Traditional mode: Provide yaml_content directly
    - Template mode: Provide template_id and variable_values
    """
    try:
        # Validate request - must have either yaml_content OR (template_id AND variable_values)
        if create_request.yaml_content and create_request.template_id:
            raise HTTPException(
                status_code=400,
                detail="请提供 yaml_content 或 template_id，不能同时提供",
            )

        if not create_request.yaml_content and not create_request.template_id:
            raise HTTPException(
                status_code=400, detail="必须提供 yaml_content 或 template_id"
            )

        template_snapshot = None
        variable_values = None
        yaml_content = create_request.yaml_content

        if yaml_content is None:
            # Template mode
            if not create_request.variable_values:
                raise HTTPException(
                    status_code=400, detail="使用模板模式时必须提供 variable_values"
                )

            # Load template
            result = await db.execute(
                select(ServerTemplate).where(
                    ServerTemplate.id == create_request.template_id
                )
            )
            template = result.scalar_one_or_none()
            if not template:
                raise HTTPException(status_code=404, detail="模板不存在")

            user_variables = deserialize_variable_definitions_json(template.variable_definitions_json)

            # Validate variable values
            errors = TemplateManager.validate_variable_values(
                user_variables, create_request.variable_values
            )
            if errors:
                raise HTTPException(status_code=400, detail=errors)

            # Render YAML
            try:
                yaml_content = TemplateManager.render_yaml(
                    template.yaml_template, create_request.variable_values
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # Store template snapshot for future editing
            template_snapshot = TemplateSnapshot(
                template_id=template.id,
                template_name=template.name,
                yaml_template=template.yaml_template,
                variable_definitions=deserialize_variable_definitions_json(template.variable_definitions_json),
                snapshot_time=datetime.now(timezone.utc).isoformat(),
            )
            variable_values = create_request.variable_values

        instance = docker_mc_manager.get_instance(server_id)

        # Check if server already exists
        if await instance.exists():
            raise HTTPException(status_code=409, detail=f"服务器 '{server_id}' 已存在")

        # Extract ports from YAML to check for conflicts
        try:
            game_port, rcon_port = extract_ports_from_yaml(yaml_content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Check for port conflicts with existing servers
        port_conflicts = await check_port_conflicts(game_port, rcon_port)
        if port_conflicts:
            conflict_messages = "; ".join(port_conflicts)
            raise HTTPException(
                status_code=409, detail=f"端口冲突: {conflict_messages}"
            )

        # Create the server using the MCInstance.create method
        await instance.create(yaml_content)

        # Create or update Server record with template info
        await create_server_record(
            db,
            server_id,
            template_id=create_request.template_id if template_snapshot else None,
            template_snapshot_json=(
                template_snapshot.model_dump_json() if template_snapshot else None
            ),
            variable_values_json=(
                json.dumps(variable_values) if variable_values else None
            ),
        )

        # Start log monitoring for the new server
        await player_system_manager.start_server_monitoring(server_id)

        return {
            "message": f"服务器 '{server_id}' 创建成功",
            "game_port": game_port,
            "rcon_port": rcon_port,
        }

    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
