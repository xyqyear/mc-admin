"""Template management API router."""

import json
from datetime import datetime, timezone

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..dependencies import get_current_user
from ..minecraft import docker_mc_manager
from ..minecraft.compose import MCComposeFile
from ..minecraft.docker.compose_file import ComposeFile
from ..models import ServerTemplate, UserPublic
from ..templates.manager import TemplateManager
from ..templates.models import (
    SYSTEM_RESERVED_VARIABLES,
    AvailablePortsResponse,
    TemplateCreateRequest,
    TemplateListItem,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateSchemaResponse,
    TemplateUpdateRequest,
    VariableDefinition,
)

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
)


def _parse_variables_json(
    variables_json: str,
) -> list[VariableDefinition]:
    """Parse variables JSON string to list of VariableDefinition."""
    raw_list = json.loads(variables_json)
    # Use Pydantic to validate and parse each variable
    from pydantic import TypeAdapter

    adapter = TypeAdapter(list[VariableDefinition])
    return adapter.validate_python(raw_list)


def _serialize_variables(variables: list[VariableDefinition]) -> str:
    """Serialize list of VariableDefinition to JSON string."""
    return json.dumps([v.model_dump() for v in variables])


@router.get("/", response_model=list[TemplateListItem])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """List all templates."""
    result = await db.execute(
        select(ServerTemplate).order_by(ServerTemplate.created_at.desc())
    )
    templates = result.scalars().all()

    return [
        TemplateListItem(
            id=t.id,
            name=t.name,
            description=t.description,
            variable_count=len(json.loads(t.variables_json))
            + len(SYSTEM_RESERVED_VARIABLES),
            created_at=t.created_at,
        )
        for t in templates
    ]


@router.get("/ports/available", response_model=AvailablePortsResponse)
async def get_available_ports(
    _: UserPublic = Depends(get_current_user),
):
    """Get suggested available ports for new server."""
    used_game_ports: set[int] = set()
    used_rcon_ports: set[int] = set()

    instances = await docker_mc_manager.get_all_instances()

    for instance in instances:
        try:
            compose_file_path = await instance.get_compose_file_path()
            if compose_file_path is None:
                continue

            compose_content = await instance.get_compose_file()
            compose_dict = yaml.safe_load(compose_content)
            compose_file = ComposeFile.from_dict(compose_dict)
            mc_compose = MCComposeFile(compose_file)
            used_game_ports.add(mc_compose.get_game_port())
            used_rcon_ports.add(mc_compose.get_rcon_port())
        except Exception:
            continue

    # Find available ports starting from common defaults
    game_port = 25565
    while game_port in used_game_ports or game_port in used_rcon_ports:
        game_port += 1

    rcon_port = 25575
    while (
        rcon_port in used_rcon_ports
        or rcon_port in used_game_ports
        or rcon_port == game_port
    ):
        rcon_port += 1

    return AvailablePortsResponse(
        suggested_game_port=game_port,
        suggested_rcon_port=rcon_port,
        used_ports=sorted(used_game_ports | used_rcon_ports),
    )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get template details."""
    result = await db.execute(
        select(ServerTemplate).where(ServerTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    user_variables = _parse_variables_json(template.variables_json)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        yaml_template=template.yaml_template,
        variables=user_variables,
        system_variables=SYSTEM_RESERVED_VARIABLES,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.post("/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: TemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Create a new template."""
    yaml_template = request.yaml_template
    variables = list(request.variables)

    # Handle copy from existing template
    if request.copy_from_template_id:
        result = await db.execute(
            select(ServerTemplate).where(
                ServerTemplate.id == request.copy_from_template_id
            )
        )
        source = result.scalar_one_or_none()
        if not source:
            raise HTTPException(status_code=404, detail="源模板不存在")

        # Use source template's content if not provided
        if not yaml_template:
            yaml_template = source.yaml_template
        if not variables:
            variables = _parse_variables_json(source.variables_json)

    # Validate template
    errors = TemplateManager.validate_template(yaml_template, variables)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Check name uniqueness
    result = await db.execute(
        select(ServerTemplate).where(ServerTemplate.name == request.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="模板名称已存在")

    template = ServerTemplate(
        name=request.name,
        description=request.description,
        yaml_template=yaml_template,
        variables_json=_serialize_variables(variables),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        yaml_template=template.yaml_template,
        variables=variables,
        system_variables=SYSTEM_RESERVED_VARIABLES,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    request: TemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Update an existing template."""
    result = await db.execute(
        select(ServerTemplate).where(ServerTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    # Update fields
    if request.name is not None:
        # Check name uniqueness
        existing = await db.execute(
            select(ServerTemplate).where(
                ServerTemplate.name == request.name, ServerTemplate.id != template_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="模板名称已存在")
        template.name = request.name

    if request.description is not None:
        template.description = request.description

    # Get current values for validation
    yaml_template = (
        request.yaml_template if request.yaml_template else template.yaml_template
    )
    variables = (
        list(request.variables)
        if request.variables is not None
        else _parse_variables_json(template.variables_json)
    )

    # Validate template
    errors = TemplateManager.validate_template(yaml_template, variables)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    if request.yaml_template is not None:
        template.yaml_template = request.yaml_template

    if request.variables is not None:
        template.variables_json = _serialize_variables(request.variables)

    template.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        yaml_template=template.yaml_template,
        variables=_parse_variables_json(template.variables_json),
        system_variables=SYSTEM_RESERVED_VARIABLES,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Delete a template."""
    result = await db.execute(
        select(ServerTemplate).where(ServerTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    await db.delete(template)
    await db.commit()


@router.get("/{template_id}/schema", response_model=TemplateSchemaResponse)
async def get_template_schema(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get JSON Schema for template variables (for rjsf form rendering)."""
    result = await db.execute(
        select(ServerTemplate).where(ServerTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    user_variables = _parse_variables_json(template.variables_json)
    json_schema = TemplateManager.generate_json_schema(user_variables)

    return TemplateSchemaResponse(
        template_id=template.id,
        template_name=template.name,
        json_schema=json_schema,
    )


@router.post("/{template_id}/preview", response_model=TemplatePreviewResponse)
async def preview_rendered_yaml(
    template_id: int,
    request: TemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Preview rendered YAML without creating server."""
    result = await db.execute(
        select(ServerTemplate).where(ServerTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    user_variables = _parse_variables_json(template.variables_json)

    # Validate values
    errors = TemplateManager.validate_variable_values(
        user_variables, request.variable_values
    )
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Render YAML
    try:
        rendered_yaml = TemplateManager.render_yaml(
            template.yaml_template, request.variable_values
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TemplatePreviewResponse(rendered_yaml=rendered_yaml)
