"""Cleanup helpers for player records excluded by identity rules."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Player, PlayerAchievement, PlayerChatMessage, PlayerSession
from ..identity_resolver import is_online_uuid
from ..name_filters import get_ignored_name_prefixes, is_ignored_player_name
from .query.player_query import _get_last_seen_expression

PlayerCleanupKind = Literal["offline_uuid", "ignored_name_prefix"]


class PlayerCleanupCandidate(BaseModel):
    player_db_id: int
    uuid: str
    current_name: str
    first_seen: datetime
    last_seen: Optional[datetime]
    session_count: int
    chat_message_count: int
    achievement_count: int


class PlayerCleanupPreviewResponse(BaseModel):
    kind: PlayerCleanupKind
    ignored_name_prefixes: list[str]
    candidates: list[PlayerCleanupCandidate]


class PlayerCleanupDeleteResponse(BaseModel):
    kind: PlayerCleanupKind
    deleted_count: int
    deleted_players: list[PlayerCleanupCandidate]


def _matches_cleanup_kind(player: Player, kind: PlayerCleanupKind) -> bool:
    if kind == "offline_uuid":
        return not is_online_uuid(player.uuid)
    return is_ignored_player_name(player.current_name)


async def _count_related_rows(
    session: AsyncSession,
    model,
    player_db_ids: list[int],
) -> dict[int, int]:
    if not player_db_ids:
        return {}

    result = await session.execute(
        select(model.player_db_id, func.count())
        .where(model.player_db_id.in_(player_db_ids))
        .group_by(model.player_db_id)
    )
    return {player_db_id: count for player_db_id, count in result.all()}


async def _get_last_seen_by_player_id(
    session: AsyncSession,
    player_db_ids: list[int],
) -> dict[int, datetime]:
    if not player_db_ids:
        return {}

    result = await session.execute(
        select(PlayerSession.player_db_id, _get_last_seen_expression())
        .where(PlayerSession.player_db_id.in_(player_db_ids))
        .group_by(PlayerSession.player_db_id)
    )

    last_seen_by_id: dict[int, datetime] = {}
    for player_db_id, last_seen in result.all():
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if last_seen is not None:
            last_seen_by_id[player_db_id] = last_seen
    return last_seen_by_id


async def get_player_cleanup_preview(
    session: AsyncSession,
    kind: PlayerCleanupKind,
) -> PlayerCleanupPreviewResponse:
    result = await session.execute(select(Player).order_by(Player.current_name.asc()))
    players = [
        player
        for player in result.scalars().all()
        if _matches_cleanup_kind(player, kind)
    ]
    player_db_ids = [player.player_db_id for player in players]

    session_counts = await _count_related_rows(session, PlayerSession, player_db_ids)
    chat_counts = await _count_related_rows(session, PlayerChatMessage, player_db_ids)
    achievement_counts = await _count_related_rows(
        session, PlayerAchievement, player_db_ids
    )
    last_seen_by_id = await _get_last_seen_by_player_id(session, player_db_ids)

    return PlayerCleanupPreviewResponse(
        kind=kind,
        ignored_name_prefixes=list(get_ignored_name_prefixes()),
        candidates=[
            PlayerCleanupCandidate(
                player_db_id=player.player_db_id,
                uuid=player.uuid,
                current_name=player.current_name,
                first_seen=player.created_at,
                last_seen=last_seen_by_id.get(player.player_db_id),
                session_count=session_counts.get(player.player_db_id, 0),
                chat_message_count=chat_counts.get(player.player_db_id, 0),
                achievement_count=achievement_counts.get(player.player_db_id, 0),
            )
            for player in players
        ],
    )


async def delete_player_cleanup_candidates(
    session: AsyncSession,
    kind: PlayerCleanupKind,
) -> PlayerCleanupDeleteResponse:
    preview = await get_player_cleanup_preview(session, kind)
    player_db_ids = [player.player_db_id for player in preview.candidates]

    if player_db_ids:
        for model in (PlayerSession, PlayerChatMessage, PlayerAchievement):
            await session.execute(
                delete(model).where(model.player_db_id.in_(player_db_ids))
            )
        await session.execute(
            delete(Player).where(Player.player_db_id.in_(player_db_ids))
        )
        await session.commit()

    return PlayerCleanupDeleteResponse(
        kind=kind,
        deleted_count=len(player_db_ids),
        deleted_players=preview.candidates,
    )
