"""CRUD operations for server records."""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Server, ServerStatus


async def get_active_servers(session: AsyncSession) -> List[Server]:
    """Get all active servers.

    Args:
        session: Database session

    Returns:
        List of active servers
    """
    result = await session.execute(
        select(Server).where(Server.status == ServerStatus.ACTIVE)
    )
    return list(result.scalars().all())


async def get_active_servers_map(session: AsyncSession) -> Dict[str, int]:
    """Get all active servers as a mapping from server_id to database ID.

    Args:
        session: Database session

    Returns:
        Dictionary mapping server_id to database ID
    """
    servers = await get_active_servers(session)
    return {server.server_id: server.id for server in servers}


async def get_server_by_id(session: AsyncSession, server_id: str) -> Optional[Server]:
    """Get a server by its identifier.

    Args:
        session: Database session
        server_id: Server identifier

    Returns:
        Server or None if not found
    """
    result = await session.execute(
        select(Server)
        .where(Server.server_id == server_id)
        .order_by(
            Server.status.asc(),
            Server.created_at.desc(),
        )
    )
    return result.scalars().first()


async def get_active_server_by_id(
    session: AsyncSession, server_id: str
) -> Server | None:
    """Get an active server by its identifier.

    Args:
        session: Database session
        server_id: Server identifier

    Returns:
        Active server or None if not found
    """
    result = await session.execute(
        select(Server).where(
            Server.server_id == server_id, Server.status == ServerStatus.ACTIVE
        )
    )
    return result.scalar_one_or_none()


async def get_server_db_id(session: AsyncSession, server_id: str) -> Optional[int]:
    """Get database ID for a server.

    Args:
        session: Database session
        server_id: Server identifier

    Returns:
        Database ID or None if not found
    """
    server = await get_server_by_id(session, server_id)
    return server.id if server else None


async def mark_server_removed(
    session: AsyncSession, server_id: str, updated_at: datetime
) -> None:
    """Mark a server as removed.

    Args:
        session: Database session
        server_id: Server identifier
        updated_at: Update timestamp
    """
    await session.execute(
        update(Server)
        .where(Server.server_id == server_id)
        .where(Server.status == ServerStatus.ACTIVE)
        .values(
            status=ServerStatus.REMOVED,
            updated_at=updated_at,
        )
    )
    await session.commit()


async def create_server_record(
    session: AsyncSession,
    server_id: str,
    template_id: Optional[int] = None,
    template_snapshot_json: Optional[str] = None,
    variable_values_json: Optional[str] = None,
) -> Server:
    """Create a new server record.

    Args:
        session: Database session
        server_id: Server identifier
        template_id: Optional template ID
        template_snapshot_json: Optional template snapshot JSON
        variable_values_json: Optional variable values JSON

    Returns:
        Created server

    Raises:
        ValueError: If an active server with the same server_id already exists
    """
    result = await session.execute(
        select(Server).where(
            Server.server_id == server_id, Server.status == ServerStatus.ACTIVE
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise ValueError(f"服务器 '{server_id}' 已存在")

    server = Server(
        server_id=server_id,
        status=ServerStatus.ACTIVE,
        template_id=template_id,
        template_snapshot_json=template_snapshot_json,
        variable_values_json=variable_values_json,
    )
    session.add(server)

    await session.commit()
    await session.refresh(server)
    return server
