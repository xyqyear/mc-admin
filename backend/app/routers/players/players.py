"""Player information API endpoints."""

import asyncio
import base64
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session, get_db
from ...dependencies import get_current_user
from ...logger import logger
from ...models import UserPublic
from ...player_locations import normalize_uuid
from ...players.crud import (
    PlayerCleanupDeleteResponse,
    PlayerCleanupKind,
    PlayerCleanupPreviewResponse,
    delete_player_cleanup_candidates,
    get_player_by_db_id,
    get_player_by_uuid as get_cached_player_by_uuid,
    get_player_cleanup_preview,
    get_players_by_uuids,
    upsert_player_profile,
)
from ...players.crud.query.player_query import (
    PlayerDetailResponse,
    PlayerSummary,
    get_all_players_summary,
    get_player_detail_by_uuid,
)
from ...players.identity_resolver import is_online_uuid
from ...players.skin_fetcher import skin_fetcher
from ...players.tracking import update_player_skin
from ...utils.sse import sse_response

router = APIRouter(prefix="/players", tags=["players"])
PROFILE_FETCH_CONCURRENCY = 8


class PlayerMapProfileResponse(BaseModel):
    player_db_id: Optional[int] = None
    uuid: str
    current_name: Optional[str] = None
    avatar_base64: Optional[str] = None
    resolved: bool
    last_skin_update: Optional[datetime] = None


class PlayerMapProfilesRequest(BaseModel):
    uuids: List[str] = Field(default_factory=list, max_length=2000)


class PlayerMapProfilesStreamEvent(BaseModel):
    event_type: Literal["profile", "complete", "error"]
    profile: Optional[PlayerMapProfileResponse] = None
    message: Optional[str] = None
    total: Optional[int] = None
    resolved: Optional[int] = None


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


def _profile_event(profile: PlayerMapProfileResponse) -> dict:
    return {
        "event_type": "profile",
        "profile": profile.model_dump(mode="json"),
    }


def _complete_event(total: int, resolved: int) -> dict:
    return {"event_type": "complete", "total": total, "resolved": resolved}


def _error_event(message: str) -> dict:
    return {"event_type": "error", "message": message}


def _dedupe_normalized_uuids(uuids: List[str]) -> tuple[list[str], list[str]]:
    normalized_uuids: list[str] = []
    invalid_uuids: list[str] = []
    seen: set[str] = set()
    for raw_uuid in uuids:
        normalized = normalize_uuid(raw_uuid)
        if normalized is None:
            if raw_uuid not in seen:
                invalid_uuids.append(raw_uuid)
                seen.add(raw_uuid)
            continue
        if normalized in seen:
            continue
        normalized_uuids.append(normalized)
        seen.add(normalized)
    return normalized_uuids, invalid_uuids


async def _client_disconnected(request: Request | None) -> bool:
    return bool(request and await request.is_disconnected())


async def iter_player_map_profile_events(
    uuids: List[str],
    request: Request | None = None,
) -> AsyncIterator[dict]:
    normalized_uuids, invalid_uuids = _dedupe_normalized_uuids(uuids)
    total = len(normalized_uuids) + len(invalid_uuids)
    resolved = 0

    for uuid in invalid_uuids:
        if await _client_disconnected(request):
            return
        yield _profile_event(PlayerMapProfileResponse(uuid=uuid, resolved=False))

    online_uuids: list[str] = []
    for uuid in normalized_uuids:
        if not is_online_uuid(uuid):
            if await _client_disconnected(request):
                return
            yield _profile_event(PlayerMapProfileResponse(uuid=uuid, resolved=False))
            continue
        online_uuids.append(uuid)

    if not online_uuids:
        yield _complete_event(total, resolved)
        return

    async with get_async_session() as db:
        cached_players = await get_players_by_uuids(db, online_uuids)

    fetch_uuids: list[str] = []
    for uuid in online_uuids:
        cached = cached_players.get(uuid)
        if cached is not None:
            if await _client_disconnected(request):
                return
            profile = _profile_response(cached, uuid)
            if profile.resolved:
                resolved += 1
            yield _profile_event(profile)
            if cached.avatar_data:
                continue
        fetch_uuids.append(uuid)

    semaphore = asyncio.Semaphore(PROFILE_FETCH_CONCURRENCY)

    async def fetch(uuid: str):
        async with semaphore:
            return uuid, await skin_fetcher.fetch_player_profile(uuid)

    tasks = {asyncio.create_task(fetch(uuid)) for uuid in fetch_uuids}
    try:
        for completed in asyncio.as_completed(tasks):
            if await _client_disconnected(request):
                return
            uuid, fetched = await completed
            if fetched is None:
                if uuid not in cached_players:
                    yield _profile_event(
                        PlayerMapProfileResponse(uuid=uuid, resolved=False)
                    )
                continue

            async with get_async_session() as db:
                player = await upsert_player_profile(
                    db,
                    uuid,
                    fetched.name,
                    fetched.skin_data,
                    fetched.avatar_data,
                    datetime.now(timezone.utc),
                )

            profile = _profile_response(player, uuid)
            if profile.resolved and uuid not in cached_players:
                resolved += 1
            yield _profile_event(profile)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    yield _complete_event(total, resolved)


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


@router.get("/cleanup/{kind}/preview", response_model=PlayerCleanupPreviewResponse)
async def preview_player_cleanup(
    kind: PlayerCleanupKind,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlayerCleanupPreviewResponse:
    return await get_player_cleanup_preview(db, kind)


@router.delete("/cleanup/{kind}", response_model=PlayerCleanupDeleteResponse)
async def delete_player_cleanup(
    kind: PlayerCleanupKind,
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlayerCleanupDeleteResponse:
    return await delete_player_cleanup_candidates(db, kind)


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


@router.post("/profiles/stream", response_class=StreamingResponse)
async def stream_player_map_profiles(
    request_body: PlayerMapProfilesRequest,
    request: Request,
    _: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream lightweight player profiles for map overlays.

    Cached rows are emitted first. Mojang fetches only run for uncached or
    avatar-missing online UUIDs, and database sessions are opened only for short
    cache/upsert operations so the stream does not hold SQLite while waiting on
    network I/O.
    """

    async def event_gen() -> AsyncIterator[dict]:
        try:
            async for event in iter_player_map_profile_events(
                request_body.uuids,
                request,
            ):
                yield event
        except Exception as e:
            logger.exception("player profile stream failed")
            yield _error_event(str(e))

    return sse_response(event_gen())


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
    if not is_online_uuid(normalized):
        return PlayerMapProfileResponse(uuid=normalized, resolved=False)

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
