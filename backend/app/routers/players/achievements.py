"""Player achievement API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...players.crud.query.achievement_query import (
    AchievementInfo,
    PlayerAchievementRank,
    get_player_achievements,
    get_server_achievement_leaderboard,
)

router = APIRouter(prefix="/players", tags=["player-achievements"])


@router.get("/{player_db_id}/achievements", response_model=List[AchievementInfo])
async def get_player_achievement_list(
    player_db_id: int,
    server_id: Optional[str] = Query(None, description="Filter by server ID"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player achievements.

    Returns a list of achievements earned by the specified player.
    """
    try:
        achievements = await get_player_achievements(
            db, player_db_id=player_db_id, server_id=server_id
        )
        return achievements
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get player achievements: {str(e)}",
        )


# Server achievement leaderboard endpoint (under /servers prefix)
server_router = APIRouter(prefix="/servers", tags=["server-achievements"])


@server_router.get(
    "/{server_id}/achievements/leaderboard", response_model=List[PlayerAchievementRank]
)
async def get_achievement_leaderboard(
    server_id: str,
    limit: int = Query(50, ge=1, le=100, description="Number of top players to return"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get server achievement leaderboard.

    Returns a leaderboard of players ranked by achievement count on the specified server.
    """
    try:
        leaderboard = await get_server_achievement_leaderboard(
            db, server_id=server_id, limit=limit
        )
        return leaderboard
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get achievement leaderboard: {str(e)}",
        )
