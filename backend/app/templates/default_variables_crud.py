"""Default variable configuration CRUD operations."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DefaultVariableConfig
from .models import (
    EnumVariableDefinition,
    IntVariableDefinition,
    StringVariableDefinition,
    VariableDefinition,
    deserialize_variable_definitions_json,
    serialize_variable_definitions,
)

# Default variables that are pre-filled when creating new templates
DEFAULT_VARIABLES: list[VariableDefinition] = [
    StringVariableDefinition(
        name="name",
        display_name="服务器名称",
        description="服务器名称，用于 container_name (mc-{name})",
        max_length=20,
        pattern="^[a-z0-9-_]+$",
    ),
    EnumVariableDefinition(
        name="java_version",
        display_name="Java 版本",
        description="服务器使用的 Java 版本",
        options=["8", "11", "17", "21", "25"],
    ),
    StringVariableDefinition(
        name="game_version",
        display_name="游戏版本",
        description="Minecraft 游戏版本",
    ),
    IntVariableDefinition(
        name="max_memory",
        display_name="最大内存 (GB)",
        description="服务器最大内存分配，单位为 GB",
        default=6,
        min_value=1,
        max_value=16,
    ),
    IntVariableDefinition(
        name="game_port",
        display_name="游戏端口",
        description="Minecraft 服务器端口",
        min_value=1024,
        max_value=65535,
    ),
    IntVariableDefinition(
        name="rcon_port",
        display_name="RCON 端口",
        description="RCON 管理端口",
        min_value=1024,
        max_value=65535,
    ),
]


async def _ensure_default_config(db: AsyncSession) -> DefaultVariableConfig:
    """Ensure default variable config exists, creating it with defaults if not.

    Args:
        db: Database session

    Returns:
        The existing or newly created config record
    """
    result = await db.execute(
        select(DefaultVariableConfig).where(DefaultVariableConfig.id == 1)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = DefaultVariableConfig(
            id=1,
            variable_definitions_json=serialize_variable_definitions(DEFAULT_VARIABLES),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

    return config


async def get_default_variables(db: AsyncSession) -> list[VariableDefinition]:
    """Get default variable configuration.

    Returns the list of default variables that are pre-filled when creating new templates.
    If no configuration exists, creates one with default values.

    Args:
        db: Database session

    Returns:
        List of variable definitions
    """
    config = await _ensure_default_config(db)
    return deserialize_variable_definitions_json(config.variable_definitions_json)


async def update_default_variables(
    db: AsyncSession,
    variables: list[VariableDefinition],
) -> list[VariableDefinition]:
    """Update default variable configuration.

    Creates or updates the default variable configuration.

    Args:
        db: Database session
        variables: List of variable definitions to save

    Returns:
        The saved list of variable definitions
    """
    result = await db.execute(
        select(DefaultVariableConfig).where(DefaultVariableConfig.id == 1)
    )
    config = result.scalar_one_or_none()

    variable_definitions_json = serialize_variable_definitions(variables)

    if config:
        config.variable_definitions_json = variable_definitions_json
        config.updated_at = datetime.now(timezone.utc)
    else:
        config = DefaultVariableConfig(
            id=1,
            variable_definitions_json=variable_definitions_json,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return deserialize_variable_definitions_json(config.variable_definitions_json)
