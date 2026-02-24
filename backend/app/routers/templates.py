"""Template management API router."""

from collections import Counter

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..dependencies import get_current_user
from ..minecraft import docker_mc_manager
from ..minecraft.compose import MCComposeFile
from ..minecraft.docker.compose_file import ComposeFile
from ..models import UserPublic
from ..templates import (
    AvailablePortsResponse,
    TemplateCreateRequest,
    TemplateListItem,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateSchemaResponse,
    TemplateUpdateRequest,
    VariableDefinition,
    check_name_exists,
    deserialize_variable_definitions_json,
    get_all_templates,
    get_default_variables,
    get_template_by_id,
    save_template,
    serialize_variable_definitions,
    update_default_variables,
)
from ..templates import create_template as create_template_crud
from ..templates import delete_template as delete_template_crud
from ..templates.manager import TemplateManager

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
)


@router.get("/", response_model=list[TemplateListItem])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """List all templates."""
    templates = await get_all_templates(db)

    return [
        TemplateListItem(
            id=t.id,
            name=t.name,
            description=t.description,
            variable_count=len(
                deserialize_variable_definitions_json(t.variable_definitions_json)
            ),
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


class DefaultVariablesResponse(BaseModel):
    """Response model for default variables."""

    variable_definitions: list[VariableDefinition]


class DefaultVariablesUpdateRequest(BaseModel):
    """Request model for updating default variables."""

    variable_definitions: list[VariableDefinition]


@router.get("/default-variables", response_model=DefaultVariablesResponse)
async def get_default_variables_endpoint(
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get default variable configuration.

    Returns the list of default variables that are pre-filled when creating new templates.
    """
    variable_definitions = await get_default_variables(db)
    return DefaultVariablesResponse(variable_definitions=variable_definitions)


@router.put("/default-variables", response_model=DefaultVariablesResponse)
async def update_default_variables_endpoint(
    request: DefaultVariablesUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Update default variable configuration.

    Updates the list of default variables that are pre-filled when creating new templates.
    """
    # Validate for duplicate names
    var_names = [v.name for v in request.variable_definitions]
    duplicates = [name for name, count in Counter(var_names).items() if count > 1]
    if duplicates:
        raise HTTPException(
            status_code=400, detail=f"变量名重复: {', '.join(sorted(duplicates))}"
        )

    variable_definitions = await update_default_variables(
        db, request.variable_definitions
    )
    return DefaultVariablesResponse(variable_definitions=variable_definitions)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get template details."""
    template = await get_template_by_id(db, template_id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    user_variables = deserialize_variable_definitions_json(
        template.variable_definitions_json
    )

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        yaml_template=template.yaml_template,
        variable_definitions=user_variables,
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
    # Validate template
    result = TemplateManager.validate_template(
        request.yaml_template, request.variable_definitions
    )
    if result.errors:
        raise HTTPException(status_code=400, detail=result.errors)

    # Check name uniqueness
    if await check_name_exists(db, request.name):
        raise HTTPException(status_code=409, detail="模板名称已存在")

    template = await create_template_crud(
        db,
        name=request.name,
        description=request.description,
        yaml_template=request.yaml_template,
        variable_definitions=request.variable_definitions,
    )

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        yaml_template=template.yaml_template,
        variable_definitions=request.variable_definitions,
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
    template = await get_template_by_id(db, template_id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    # Check name uniqueness if name is being updated
    if request.name is not None:
        if await check_name_exists(db, request.name, exclude_id=template_id):
            raise HTTPException(status_code=409, detail="模板名称已存在")

    # Get current values for validation
    yaml_template = (
        request.yaml_template if request.yaml_template else template.yaml_template
    )
    variable_definitions = (
        request.variable_definitions
        if request.variable_definitions is not None
        else deserialize_variable_definitions_json(template.variable_definitions_json)
    )

    # Validate template
    result = TemplateManager.validate_template(yaml_template, variable_definitions)
    if result.errors:
        raise HTTPException(status_code=400, detail=result.errors)

    # Update template fields
    if request.name is not None:
        template.name = request.name
    if request.description is not None:
        template.description = request.description
    if request.yaml_template is not None:
        template.yaml_template = request.yaml_template
    if request.variable_definitions is not None:
        template.variable_definitions_json = serialize_variable_definitions(
            request.variable_definitions
        )

    # Save updates
    await save_template(db, template)

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        yaml_template=template.yaml_template,
        variable_definitions=deserialize_variable_definitions_json(
            template.variable_definitions_json
        ),
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
    template = await get_template_by_id(db, template_id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    await delete_template_crud(db, template)


@router.get("/{template_id}/schema", response_model=TemplateSchemaResponse)
async def get_template_schema(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Get JSON Schema for template variables (for rjsf form rendering)."""
    template = await get_template_by_id(db, template_id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    user_variables = deserialize_variable_definitions_json(
        template.variable_definitions_json
    )
    yaml_variables = TemplateManager.filter_yaml_variables(
        template.yaml_template, user_variables
    )
    json_schema = TemplateManager.generate_json_schema(yaml_variables)

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
    template = await get_template_by_id(db, template_id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    user_variables = deserialize_variable_definitions_json(
        template.variable_definitions_json
    )
    yaml_variables = TemplateManager.filter_yaml_variables(
        template.yaml_template, user_variables
    )

    # Validate values
    errors = TemplateManager.validate_variable_values(
        yaml_variables, request.variable_values
    )
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    # Render YAML
    try:
        rendered_yaml = TemplateManager.render_yaml(
            template.yaml_template, request.variable_values
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TemplatePreviewResponse(rendered_yaml=rendered_yaml)
