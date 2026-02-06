"""ServerTemplate CRUD operations."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ServerTemplate
from .models import VariableDefinition, serialize_variable_definitions


async def get_all_templates(session: AsyncSession) -> list[ServerTemplate]:
    """Get all templates ordered by creation date descending.

    Args:
        session: Database session

    Returns:
        List of all templates
    """
    result = await session.execute(
        select(ServerTemplate).order_by(ServerTemplate.created_at.desc())
    )
    return list(result.scalars().all())


async def get_template_by_id(
    session: AsyncSession, template_id: int
) -> Optional[ServerTemplate]:
    """Get a template by its ID.

    Args:
        session: Database session
        template_id: Template ID

    Returns:
        Template if found, None otherwise
    """
    result = await session.execute(
        select(ServerTemplate).where(ServerTemplate.id == template_id)
    )
    return result.scalar_one_or_none()


async def get_template_by_name(
    session: AsyncSession, name: str
) -> Optional[ServerTemplate]:
    """Get a template by its name.

    Args:
        session: Database session
        name: Template name

    Returns:
        Template if found, None otherwise
    """
    result = await session.execute(
        select(ServerTemplate).where(ServerTemplate.name == name)
    )
    return result.scalar_one_or_none()


async def check_name_exists(
    session: AsyncSession, name: str, exclude_id: Optional[int] = None
) -> bool:
    """Check if a template name already exists.

    Args:
        session: Database session
        name: Template name to check
        exclude_id: Optional template ID to exclude from check (for updates)

    Returns:
        True if name exists, False otherwise
    """
    query = select(ServerTemplate).where(ServerTemplate.name == name)
    if exclude_id is not None:
        query = query.where(ServerTemplate.id != exclude_id)
    result = await session.execute(query)
    return result.scalar_one_or_none() is not None


async def create_template(
    session: AsyncSession,
    name: str,
    description: Optional[str],
    yaml_template: str,
    variable_definitions: list[VariableDefinition],
) -> ServerTemplate:
    """Create a new template.

    Args:
        session: Database session
        name: Template name
        description: Template description
        yaml_template: YAML template content
        variable_definitions: List of variable definitions

    Returns:
        Created template
    """
    template = ServerTemplate(
        name=name,
        description=description,
        yaml_template=yaml_template,
        variable_definitions_json=serialize_variable_definitions(variable_definitions),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def save_template(session: AsyncSession, template: ServerTemplate) -> None:
    """Save changes to a template.

    Updates the updated_at timestamp and commits changes.

    Args:
        session: Database session
        template: Template with modifications
    """
    template.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(template)


async def delete_template(session: AsyncSession, template: ServerTemplate) -> None:
    """Delete a template.

    Args:
        session: Database session
        template: Template to delete
    """
    await session.delete(template)
    await session.commit()
