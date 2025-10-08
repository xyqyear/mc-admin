"""Player session API endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...players.crud.query.session_query import (
    OnlinePlayerInfo,
    SessionInfo,
    SessionStatsResponse,
    get_player_session_stats,
    get_player_sessions,
    get_server_online_players,
)

router = APIRouter(prefix="/players", tags=["player-sessions"])


@router.get("/{player_db_id}/sessions", response_model=List[SessionInfo])
async def get_player_session_list(
    player_db_id: int,
    limit: int = Query(100, ge=1, le=500, description="Maximum sessions to return"),
    server_id: Optional[str] = Query(None, description="Filter by server ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player session history.

    Returns a list of gaming sessions for the specified player.
    """
    try:
        sessions = await get_player_sessions(
            db,
            player_db_id=player_db_id,
            limit=limit,
            server_id=server_id,
            start_date=start_date,
            end_date=end_date,
        )
        return sessions
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get player sessions: {str(e)}",
        )


@router.get("/{player_db_id}/sessions/stats", response_model=SessionStatsResponse)
async def get_player_session_statistics(
    player_db_id: int,
    period: str = Query("all", regex="^(all|week|month|year)$"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player session statistics.

    Returns aggregated statistics about player's gaming sessions.
    """
    try:
        stats = await get_player_session_stats(
            db, player_db_id=player_db_id, period=period
        )
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session stats: {str(e)}",
        )


# Server online players endpoint (under /servers prefix)
server_router = APIRouter(prefix="/servers", tags=["server-online-players"])


@server_router.get("/{server_id}/online-players", response_model=List[OnlinePlayerInfo])
async def get_server_online_player_list(
    server_id: str,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get currently online players on a server.

    Returns a list of players currently online on the specified server
    with their session information.
    """
    try:
        online_players = await get_server_online_players(db, server_id=server_id)
        return online_players
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get online players: {str(e)}",
        )
