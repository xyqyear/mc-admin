"""Player information API endpoints."""

import base64
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...player_locations import normalize_uuid
from ...players.crud import (
    get_player_avatar_data,
    get_player_by_db_id,
    get_player_by_uuid as get_cached_player_by_uuid,
    get_player_skin_data,
    upsert_player_profile,
)
from ...players.crud.query.player_query import (
    PlayerDetailResponse,
    PlayerSummary,
    get_all_players_summary,
    get_player_detail_by_name,
    get_player_detail_by_uuid,
)
from ...players.skin_fetcher import skin_fetcher
from ...players.tracking import update_player_skin

router = APIRouter(prefix="/players", tags=["players"])


class PlayerMapProfileResponse(BaseModel):
    player_db_id: Optional[int] = None
    uuid: str
    current_name: Optional[str] = None
    avatar_base64: Optional[str] = None
    resolved: bool
    last_skin_update: Optional[datetime] = None


def _avatar_base64(avatar_data: Optional[bytes]) -> Optional[str]:
    if not avatar_data:
        return None
    return base64.b64encode(avatar_data).decode("utf-8")


def _profile_response(player, uuid: str) -> PlayerMapProfileResponse:
    if player is None:
        return PlayerMapProfileResponse(uuid=uuid, resolved=False)
    return PlayerMapProfileResponse(
        player_db_id=player.player_db_id,
        uuid=player.uuid,
        current_name=player.current_name,
        avatar_base64=_avatar_base64(player.avatar_data),
        resolved=True,
        last_skin_update=player.last_skin_update,
    )


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


@router.get("/uuid/{uuid}/profile", response_model=PlayerMapProfileResponse)
async def get_player_map_profile(
    uuid: str,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlayerMapProfileResponse:
    """
    Resolve a lightweight player profile for map overlays.

    Returns cached player data when possible. Mojang failures are represented
    as unresolved 200 responses so player-location rendering is never blocked
    by external availability.
    """
    normalized = normalize_uuid(uuid)
    if normalized is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID",
        )

    cached = await get_cached_player_by_uuid(db, normalized)
    if cached is not None and cached.avatar_data:
        return _profile_response(cached, normalized)

    fetched = await skin_fetcher.fetch_player_profile(normalized)
    if fetched is None:
        return _profile_response(cached, normalized)

    player = await upsert_player_profile(
        db,
        normalized,
        fetched.name,
        fetched.skin_data,
        fetched.avatar_data,
        datetime.now(timezone.utc),
    )
    return _profile_response(player, normalized)


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
