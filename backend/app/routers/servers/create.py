"""Server creation API router supporting both traditional YAML and template modes."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...logger import logger
from ...minecraft import docker_mc_manager
from ...minecraft.compose import MCComposeFile
from ...minecraft.docker.compose_file import ComposeFile
from ...models import Server, ServerStatus, ServerTemplate, UserPublic
from ...players import player_system_manager
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


# Helper functions for port conflict checking
def extract_ports_from_yaml(yaml_content: str) -> tuple[int, int]:
    """Extract game port and RCON port from YAML content.

    Args:
        yaml_content: Docker Compose YAML content

    Returns:
        tuple[int, int]: (game_port, rcon_port)

    Raises:
        ValueError: If YAML is invalid or doesn't contain required ports
    """
    # Parse YAML and create compose objects
    compose_dict = yaml.safe_load(yaml_content)
    compose_file = ComposeFile.from_dict(compose_dict)
    mc_compose = MCComposeFile(compose_file)

    # Extract ports using existing methods
    game_port = mc_compose.get_game_port()
    rcon_port = mc_compose.get_rcon_port()

    return game_port, rcon_port


async def check_port_conflicts(game_port: int, rcon_port: int) -> list[str]:
    """Check for port conflicts with existing servers.

    Args:
        game_port: Game port to check
        rcon_port: RCON port to check

    Returns:
        list[str]: List of conflict messages, empty if no conflicts
    """
    conflicts = []

    # Get all existing instances
    instances = await docker_mc_manager.get_all_instances()

    for instance in instances:
        # Get compose file path to check if server exists
        compose_file_path = await instance.get_compose_file_path()
        if compose_file_path is None:
            # Server doesn't have compose file yet, skip
            continue

        try:
            # Parse compose file directly to get port information
            compose_content = await instance.get_compose_file()
            existing_game_port, existing_rcon_port = extract_ports_from_yaml(
                compose_content
            )
        except Exception:
            logger.warning(
                f"Failed to parse compose file for {instance.get_name()} while checking port conflicts"
            )
            # If we can't parse this server's ports, skip it
            continue

        # Check game port conflict
        if existing_game_port == game_port:
            conflicts.append(
                f"Game port {game_port} is already used by server '{instance.get_name()}'"
            )

        # Check RCON port conflict
        if existing_rcon_port == rcon_port:
            conflicts.append(
                f"RCON port {rcon_port} is already used by server '{instance.get_name()}'"
            )

    return conflicts


def _parse_variables_json(variables_json: str) -> list:
    """Parse variables JSON string to list of VariableDefinition."""
    from pydantic import TypeAdapter

    from ...templates.models import VariableDefinition

    raw_list = json.loads(variables_json)
    adapter = TypeAdapter(list[VariableDefinition])
    return adapter.validate_python(raw_list)


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

        if create_request.template_id:
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

            user_variables = _parse_variables_json(template.variables_json)

            # Validate variable values
            errors = TemplateManager.validate_variable_values(
                user_variables, create_request.variable_values
            )
            if errors:
                raise HTTPException(status_code=400, detail={"errors": errors})

            # Render YAML
            try:
                yaml_content = TemplateManager.render_yaml(
                    template.yaml_template, create_request.variable_values
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # Store template snapshot for future editing
            template_snapshot = {
                "template_id": template.id,
                "template_name": template.name,
                "yaml_template": template.yaml_template,
                "variables": json.loads(template.variables_json),
                "snapshot_time": datetime.now(timezone.utc).isoformat(),
            }
            variable_values = create_request.variable_values

        instance = docker_mc_manager.get_instance(server_id)

        # Check if server already exists
        if await instance.exists():
            raise HTTPException(
                status_code=409, detail=f"服务器 '{server_id}' 已存在"
            )

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

        # Update or create Server record with template info
        server_record = await db.execute(
            select(Server).where(
                Server.server_id == server_id, Server.status == ServerStatus.ACTIVE
            )
        )
        server = server_record.scalar_one_or_none()

        if server:
            # Update existing record
            if template_snapshot:
                server.template_id = create_request.template_id
                server.template_snapshot_json = json.dumps(template_snapshot)
                server.variable_values_json = json.dumps(variable_values)
            server.updated_at = datetime.now(timezone.utc)
        else:
            # Create new record
            server = Server(
                server_id=server_id,
                status=ServerStatus.ACTIVE,
                template_id=create_request.template_id if template_snapshot else None,
                template_snapshot_json=(
                    json.dumps(template_snapshot) if template_snapshot else None
                ),
                variable_values_json=(
                    json.dumps(variable_values) if variable_values else None
                ),
            )
            db.add(server)

        await db.commit()

        # Trigger immediate sync to start log monitoring
        asyncio.create_task(player_system_manager.sync_servers())

        return {
            "message": f"服务器 '{server_id}' 创建成功",
            "game_port": game_port,
            "rcon_port": rcon_port,
        }

    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
