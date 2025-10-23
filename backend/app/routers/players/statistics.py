"""Player statistics API endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...players.crud.query.statistics_query import (
    ActivityDataPoint,
    GlobalPlayerStats,
    ServerPlayerStats,
    get_activity_trend,
    get_global_player_stats,
    get_server_player_stats,
)

router = APIRouter(prefix="/players", tags=["player-statistics"])


@router.get("/statistics/overview", response_model=GlobalPlayerStats)
async def get_player_statistics_overview(
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get global player statistics overview.

    Returns aggregated statistics for all players across all servers.
    """
    return await get_global_player_stats(db)


@router.get("/statistics/activity-trend", response_model=List[ActivityDataPoint])
async def get_player_activity_trend(
    period: str = Query("week", regex="^(week|month|year)$"),
    interval: str = Query("day", regex="^(hour|day|week)$"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player activity trend.

    Returns activity trend data points showing player activity over time.
    """
    return await get_activity_trend(db, period=period, interval=interval)


# Server statistics endpoint (under /servers prefix)
server_router = APIRouter(prefix="/servers", tags=["server-statistics"])


@server_router.get("/{server_id}/statistics/players", response_model=ServerPlayerStats)
async def get_server_player_statistics(
    server_id: str,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get server player statistics.

    Returns aggregated player statistics for the specified server.
    """
    stats = await get_server_player_stats(db, server_id=server_id)
    if not stats:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found",
        )
    return stats
