"""Player achievement API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...players.crud.query.achievement_query import (
    AchievementInfo,
    get_player_achievements,
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
    achievements = await get_player_achievements(
        db, player_db_id=player_db_id, server_id=server_id
    )
    return achievements
