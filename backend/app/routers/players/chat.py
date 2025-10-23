"""Player chat message API endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...players.crud.query.chat_query import (
    ChatMessageInfo,
    ChatMessageWithPlayer,
    get_player_chat_messages,
    get_server_chat_messages,
)

router = APIRouter(prefix="/players", tags=["player-chat"])


@router.get("/{player_db_id}/chat", response_model=List[ChatMessageInfo])
async def get_player_chat(
    player_db_id: int,
    limit: int = Query(100, ge=1, le=500, description="Maximum messages to return"),
    server_id: Optional[str] = Query(None, description="Filter by server ID"),
    search: Optional[str] = Query(None, description="Search in message text"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player chat messages.

    Returns a list of chat messages sent by the specified player.
    """
    messages = await get_player_chat_messages(
        db,
        player_db_id=player_db_id,
        limit=limit,
        server_id=server_id,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )
    return messages


# Server chat endpoint (under /servers prefix)
server_router = APIRouter(prefix="/servers", tags=["server-chat"])


@server_router.get("/{server_id}/chat", response_model=List[ChatMessageWithPlayer])
async def get_server_chat(
    server_id: str,
    limit: int = Query(100, ge=1, le=500, description="Maximum messages to return"),
    search: Optional[str] = Query(None, description="Search in message text"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get server chat messages.

    Returns a list of chat messages from the specified server with player information.
    """
    messages = await get_server_chat_messages(
        db,
        server_id=server_id,
        limit=limit,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )
    return messages
