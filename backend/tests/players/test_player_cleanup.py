from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dynamic_config.configs.players import PlayersConfig
from app.models import (
    Base,
    Player,
    PlayerAchievement,
    PlayerChatMessage,
    PlayerSession,
    Server,
    ServerStatus,
)
from app.players.crud.player_cleanup import (
    delete_player_cleanup_candidates,
    get_player_cleanup_preview,
)
from tests.players.helpers import make_offline_uuid, make_online_uuid


@pytest.fixture
async def test_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


def _set_ignored_player_prefixes(monkeypatch, prefixes: list[str]) -> None:
    runtime_config = SimpleNamespace(
        players=PlayersConfig(ignored_name_prefixes=prefixes)
    )
    monkeypatch.setattr("app.players.name_filters.config", runtime_config)


async def _add_player(
    session: AsyncSession,
    player_db_id: int,
    name: str,
    uuid: str,
) -> Player:
    player = Player(
        player_db_id=player_db_id,
        uuid=uuid,
        current_name=name,
        created_at=datetime.now(timezone.utc),
    )
    session.add(player)
    await session.commit()
    return player


@pytest.mark.asyncio
async def test_offline_uuid_cleanup_deletes_player_and_related_rows(
    test_db_session,
):
    server = Server(id=1, server_id="test", status=ServerStatus.ACTIVE)
    test_db_session.add(server)

    offline_player = await _add_player(
        test_db_session,
        1,
        "OfflinePlayer",
        make_offline_uuid("OfflinePlayer"),
    )
    online_player = await _add_player(
        test_db_session,
        2,
        "OnlinePlayer",
        make_online_uuid("OnlinePlayer"),
    )

    joined_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    left_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    test_db_session.add_all(
        [
            PlayerSession(
                player_db_id=offline_player.player_db_id,
                server_db_id=server.id,
                joined_at=joined_at,
                left_at=left_at,
                duration_seconds=300,
            ),
            PlayerSession(
                player_db_id=online_player.player_db_id,
                server_db_id=server.id,
                joined_at=joined_at,
                left_at=left_at,
                duration_seconds=300,
            ),
            PlayerChatMessage(
                player_db_id=offline_player.player_db_id,
                server_db_id=server.id,
                message_text="hello",
                sent_at=joined_at,
            ),
            PlayerAchievement(
                player_db_id=offline_player.player_db_id,
                server_db_id=server.id,
                achievement_name="Stone Age",
                earned_at=joined_at,
            ),
        ]
    )
    await test_db_session.commit()

    preview = await get_player_cleanup_preview(test_db_session, "offline_uuid")

    assert [player.current_name for player in preview.candidates] == ["OfflinePlayer"]
    assert preview.candidates[0].session_count == 1
    assert preview.candidates[0].chat_message_count == 1
    assert preview.candidates[0].achievement_count == 1
    assert preview.candidates[0].last_seen == left_at

    deleted = await delete_player_cleanup_candidates(test_db_session, "offline_uuid")

    assert deleted.deleted_count == 1
    assert [player.current_name for player in deleted.deleted_players] == [
        "OfflinePlayer"
    ]

    remaining_players = (
        await test_db_session.execute(select(Player.current_name))
    ).scalars().all()
    assert remaining_players == ["OnlinePlayer"]

    remaining_sessions = (
        await test_db_session.execute(select(PlayerSession.player_db_id))
    ).scalars().all()
    assert remaining_sessions == [online_player.player_db_id]

    assert (
        await test_db_session.execute(select(PlayerChatMessage))
    ).scalar_one_or_none() is None
    assert (
        await test_db_session.execute(select(PlayerAchievement))
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_ignored_prefix_cleanup_uses_current_config(
    test_db_session,
    monkeypatch,
):
    _set_ignored_player_prefixes(monkeypatch, ["bot_", "npc_"])

    await _add_player(
        test_db_session,
        1,
        "BOT_Carpet",
        make_online_uuid("BOT_Carpet"),
    )
    await _add_player(
        test_db_session,
        2,
        "npc_Guide",
        make_online_uuid("npc_Guide"),
    )
    await _add_player(
        test_db_session,
        3,
        "Steve",
        make_online_uuid("Steve"),
    )

    preview = await get_player_cleanup_preview(test_db_session, "ignored_name_prefix")

    assert preview.ignored_name_prefixes == ["bot_", "npc_"]
    assert [player.current_name for player in preview.candidates] == [
        "BOT_Carpet",
        "npc_Guide",
    ]

    deleted = await delete_player_cleanup_candidates(
        test_db_session,
        "ignored_name_prefix",
    )

    assert deleted.deleted_count == 2
    remaining_players = (
        await test_db_session.execute(select(Player.current_name))
    ).scalars().all()
    assert remaining_players == ["Steve"]
