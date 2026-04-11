"""Player information API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...players.crud import get_player_avatar_data, get_player_by_db_id, get_player_skin_data
from ...players.crud.query.player_query import (
    PlayerDetailResponse,
    PlayerSummary,
    get_all_players_summary,
    get_player_detail_by_name,
    get_player_detail_by_uuid,
)
from ...players.tracking import update_player_skin

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/", response_model=List[PlayerSummary])
async def get_all_players(
    online_only: bool = Query(False, description="Only return online players"),
    server_id: Optional[str] = Query(None, description="Filter by server ID"),
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all players summary.

    Returns a list of all players with basic information and statistics.
    """
    players = await get_all_players_summary(
        db, online_only=online_only, server_id=server_id
    )
    return players


@router.get("/uuid/{uuid}", response_model=PlayerDetailResponse)
async def get_player_by_uuid(
    uuid: str,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player detail by UUID.

    Returns detailed information about a player including statistics and current status.
    """
    player_detail = await get_player_detail_by_uuid(db, uuid)
    if not player_detail:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Player with UUID '{uuid}' not found",
        )
    return player_detail


@router.get("/name/{name}", response_model=PlayerDetailResponse)
async def get_player_by_name(
    name: str,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player detail by name.

    Returns detailed information about a player including statistics and current status.
    """
    player_detail = await get_player_detail_by_name(db, name)
    if not player_detail:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Player with name '{name}' not found",
        )
    return player_detail


@router.get("/{player_db_id}/avatar")
async def get_player_avatar(
    player_db_id: int,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player avatar image.

    Returns the player's avatar as a PNG image.
    """
    avatar_data = await get_player_avatar_data(db, player_db_id)

    if not avatar_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Player avatar not found",
        )

    return Response(content=avatar_data, media_type="image/png")


@router.get("/{player_db_id}/skin")
async def get_player_skin(
    player_db_id: int,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get player skin image.

    Returns the player's skin as a PNG image.
    """
    skin_data = await get_player_skin_data(db, player_db_id)

    if not skin_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Player skin not found",
        )

    return Response(content=skin_data, media_type="image/png")


@router.post("/{player_db_id}/refresh-skin")
async def refresh_player_skin(
    player_db_id: int,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh player skin.

    Triggers a skin update request for the specified player.
    """
    player = await get_player_by_db_id(db, player_db_id)

    if not player:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )

    await update_player_skin(player.player_db_id, player.uuid, player.current_name)

    return {"message": "Skin refresh requested"}
