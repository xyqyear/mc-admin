"""Chat query functions for API endpoints."""

import base64
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Player, PlayerChatMessage, Server
from ....servers.crud import get_server_db_id


class ChatMessageInfo(BaseModel):
    """Chat message information."""

    message_id: int
    server_db_id: int
    server_id: str
    message_text: str
    sent_at: datetime


class ChatMessageWithPlayer(BaseModel):
    """Chat message with player information."""

    message_id: int
    player_db_id: int
    player_name: str
    player_avatar_base64: Optional[str]
    message_text: str
    sent_at: datetime


async def get_player_chat_messages(
    session: AsyncSession,
    player_db_id: int,
    limit: int = 100,
    server_id: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[ChatMessageInfo]:
    """Get player chat messages.

    Args:
        session: Database session
        player_db_id: Player database ID
        limit: Maximum number of messages to return
        server_id: Filter by server ID
        search: Search in message text
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of chat messages
    """
    # Base query
    query = (
        select(PlayerChatMessage, Server.server_id)
        .join(Server, PlayerChatMessage.server_db_id == Server.id)
        .where(PlayerChatMessage.player_db_id == player_db_id)
        .order_by(PlayerChatMessage.sent_at.desc())
        .limit(limit)
    )

    # Build filters
    filters = []

    if server_id:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id:
            filters.append(PlayerChatMessage.server_db_id == server_db_id)

    if search:
        filters.append(PlayerChatMessage.message_text.contains(search))

    if start_date:
        filters.append(PlayerChatMessage.sent_at >= start_date)

    if end_date:
        filters.append(PlayerChatMessage.sent_at <= end_date)

    if filters:
        query = query.where(and_(*filters))

    result = await session.execute(query)
    rows = result.all()

    messages = []
    for row in rows:
        chat_message = row[0]
        server_id_str = row[1]

        messages.append(
            ChatMessageInfo(
                message_id=chat_message.message_id,
                server_db_id=chat_message.server_db_id,
                server_id=server_id_str,
                message_text=chat_message.message_text,
                sent_at=chat_message.sent_at,
            )
        )

    return messages


async def get_server_chat_messages(
    session: AsyncSession,
    server_id: str,
    limit: int = 100,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[ChatMessageWithPlayer]:
    """Get server chat messages.

    Args:
        session: Database session
        server_id: Server ID
        limit: Maximum number of messages to return
        search: Search in message text
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of chat messages with player info
    """
    server_db_id = await get_server_db_id(session, server_id)
    if server_db_id is None:
        return []

    # Base query
    query = (
        select(PlayerChatMessage, Player)
        .join(Player, PlayerChatMessage.player_db_id == Player.player_db_id)
        .where(PlayerChatMessage.server_db_id == server_db_id)
        .order_by(PlayerChatMessage.sent_at.desc())
        .limit(limit)
    )

    # Build filters
    filters = []

    if search:
        filters.append(PlayerChatMessage.message_text.contains(search))

    if start_date:
        filters.append(PlayerChatMessage.sent_at >= start_date)

    if end_date:
        filters.append(PlayerChatMessage.sent_at <= end_date)

    if filters:
        query = query.where(and_(*filters))

    result = await session.execute(query)
    rows = result.all()

    messages = []
    for row in rows:
        chat_message = row[0]
        player = row[1]

        avatar_base64 = (
            base64.b64encode(player.avatar_data).decode("utf-8")
            if player.avatar_data
            else None
        )

        messages.append(
            ChatMessageWithPlayer(
                message_id=chat_message.message_id,
                player_db_id=player.player_db_id,
                player_name=player.current_name,
                player_avatar_base64=avatar_base64,
                message_text=chat_message.message_text,
                sent_at=chat_message.sent_at,
            )
        )

    return messages
