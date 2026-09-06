from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Player,
    PlayerAchievement,
    PlayerChatMessage,
    PlayerSession,
    Server,
)
from app.players.crud.query.achievement_query import get_player_achievements
from app.players.crud.query.chat_query import get_player_chat_messages
from app.players.crud.query.session_query import get_player_sessions
from tests.players.helpers import make_online_uuid


@pytest.fixture
async def player_history():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            player = Player(uuid=make_online_uuid("filtered"), current_name="Filtered")
            other = Player(uuid=make_online_uuid("other"), current_name="Other")
            servers = [Server(server_id=name) for name in ("alpha", "beta")]
            session.add_all([player, other, *servers])
            await session.flush()
            now = datetime.now(UTC)
            for owner in (player, other):
                for server in servers:
                    session.add_all(
                        [
                            PlayerSession(
                                player_db_id=owner.player_db_id,
                                server_db_id=server.id,
                                joined_at=now,
                                left_at=None,
                                duration_seconds=None,
                            ),
                            PlayerChatMessage(
                                player_db_id=owner.player_db_id,
                                server_db_id=server.id,
                                message_text=f"{owner.current_name} on {server.server_id}",
                                sent_at=now,
                            ),
                            PlayerAchievement(
                                player_db_id=owner.player_db_id,
                                server_db_id=server.id,
                                achievement_name="Stone Age",
                                earned_at=now,
                            ),
                        ]
                    )
            await session.commit()
            yield session, player.player_db_id
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "query",
    [get_player_sessions, get_player_chat_messages, get_player_achievements],
    ids=["sessions", "chat", "achievements"],
)
@pytest.mark.parametrize(
    "server_id,expected",
    [(None, {"alpha", "beta"}), ("alpha", {"alpha"}), ("beta", {"beta"}), ("missing", set())],
    ids=["unfiltered", "alpha", "beta", "unknown"],
)
async def test_player_history_respects_server_filter(player_history, query, server_id, expected):
    session, player_db_id = player_history
    rows = await query(session, player_db_id, server_id=server_id)
    assert {row.server_id for row in rows} == expected
    assert len(rows) == len(expected)
