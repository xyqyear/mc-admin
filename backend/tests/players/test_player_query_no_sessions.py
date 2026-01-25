"""Test player query functions for players without sessions.

This test specifically addresses the bug where players without any sessions
would incorrectly show last_seen as current_timestamp instead of NULL.

Bug fix: In _get_last_seen_expression(), the condition `PlayerSession.left_at == None`
would match both:
1. Players with online sessions (left_at IS NULL)
2. Players with no sessions (all PlayerSession fields are NULL from outerjoin)

The fix adds a check for `PlayerSession.session_id != None` to distinguish between
these two cases.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Player, PlayerSession, Server
from app.players.crud.query.player_query import (
    get_all_players_summary,
    get_player_last_seen,
)


async def create_test_db():
    """Create a temporary test database and return session."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db_path = Path(temp_db.name)
    temp_db.close()

    database_url = f"sqlite+aiosqlite:///{temp_db_path}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    session = async_session()

    return session, engine, temp_db_path


async def cleanup_test_db(session, engine, temp_db_path):
    """Cleanup test database."""
    await session.close()
    await engine.dispose()
    temp_db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_player_without_sessions_has_null_last_seen():
    """Test that a player without any sessions has last_seen=NULL.

    This is a regression test for the bug where players without sessions
    would incorrectly show last_seen as current_timestamp.
    """
    db, engine, temp_db_path = await create_test_db()

    try:
        test_player_uuid = "test-uuid-no-sessions-001"

        # Create test server
        test_server = Server(
            server_id="test_server_no_sessions",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_server)
        await db.flush()

        # Create test player WITHOUT any sessions
        test_player = Player(
            uuid=test_player_uuid,
            current_name="PlayerNoSessions",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_player)
        await db.commit()

        # Get player summary
        players_summary = await get_all_players_summary(db)
        test_player_summary = next(
            (p for p in players_summary if p.uuid == test_player_uuid), None
        )

        assert test_player_summary is not None, "Test player not found in summary"

        # CRITICAL: Player without sessions should have last_seen=NULL
        assert test_player_summary.last_seen is None, (
            f"Player without sessions should have last_seen=NULL, "
            f"but got {test_player_summary.last_seen}"
        )

        # Player should be offline
        assert test_player_summary.is_online is False, "Player should be offline"

        # Player should have 0 playtime
        assert test_player_summary.total_playtime_seconds == 0, (
            f"Player without sessions should have 0 playtime, "
            f"but got {test_player_summary.total_playtime_seconds}"
        )

        print("✓ Player without sessions correctly has last_seen=NULL")

        # Also test get_player_last_seen directly
        last_seen = await get_player_last_seen(db, test_player.player_db_id)
        assert last_seen is None, (
            f"get_player_last_seen should return None for player without sessions, "
            f"but got {last_seen}"
        )

        print("✓ get_player_last_seen correctly returns None")

    finally:
        await cleanup_test_db(db, engine, temp_db_path)


@pytest.mark.asyncio
async def test_player_with_offline_session_has_left_at_as_last_seen():
    """Test that a player with offline sessions has last_seen=left_at."""
    db, engine, temp_db_path = await create_test_db()

    try:
        test_player_uuid = "test-uuid-offline-002"

        # Create test server
        test_server = Server(
            server_id="test_server_offline",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_server)
        await db.flush()

        # Create test player
        test_player = Player(
            uuid=test_player_uuid,
            current_name="PlayerOffline",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_player)
        await db.flush()

        # Create offline session
        left_time = datetime.now(timezone.utc) - timedelta(hours=1)
        session = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=left_time - timedelta(hours=2),
            left_at=left_time,
            duration_seconds=7200,
        )
        db.add(session)
        await db.commit()

        # Get player summary
        players_summary = await get_all_players_summary(db)
        test_player_summary = next(
            (p for p in players_summary if p.uuid == test_player_uuid), None
        )

        assert test_player_summary is not None

        # last_seen should equal left_at
        assert test_player_summary.last_seen is not None, "last_seen should not be NULL"
        assert abs((test_player_summary.last_seen - left_time).total_seconds()) < 1, (
            f"last_seen should equal left_at ({left_time}), "
            f"but got {test_player_summary.last_seen}"
        )

        # Player should be offline
        assert test_player_summary.is_online is False, "Player should be offline"

        print(
            f"✓ Player with offline session has last_seen={test_player_summary.last_seen}"
        )

    finally:
        await cleanup_test_db(db, engine, temp_db_path)


@pytest.mark.asyncio
async def test_player_with_online_session_has_current_time_as_last_seen():
    """Test that a player with an online session has last_seen=current_timestamp."""
    db, engine, temp_db_path = await create_test_db()

    try:
        test_player_uuid = "test-uuid-online-003"

        # Create test server
        test_server = Server(
            server_id="test_server_online",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_server)
        await db.flush()

        # Create test player
        test_player = Player(
            uuid=test_player_uuid,
            current_name="PlayerOnline",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_player)
        await db.flush()

        # Create online session (left_at=NULL)
        session = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            left_at=None,  # Online
            duration_seconds=None,
        )
        db.add(session)
        await db.commit()

        # Get player summary
        players_summary = await get_all_players_summary(db)
        test_player_summary = next(
            (p for p in players_summary if p.uuid == test_player_uuid), None
        )

        assert test_player_summary is not None

        # last_seen should be very recent (current_timestamp)
        assert test_player_summary.last_seen is not None, "last_seen should not be NULL"
        now = datetime.now(timezone.utc)
        time_diff = abs((test_player_summary.last_seen - now).total_seconds())
        assert time_diff < 2, (
            f"Online player's last_seen should be current_timestamp, "
            f"but time difference is {time_diff} seconds"
        )

        # Player should be online
        assert test_player_summary.is_online is True, "Player should be online"

        print(
            f"✓ Player with online session has last_seen={test_player_summary.last_seen} (current time)"
        )

    finally:
        await cleanup_test_db(db, engine, temp_db_path)


@pytest.mark.asyncio
async def test_multiple_players_mixed_session_states():
    """Test multiple players with different session states in one query.

    This ensures the fix works correctly when querying multiple players
    with different session states simultaneously.
    """
    db, engine, temp_db_path = await create_test_db()

    try:
        # Create test server
        test_server = Server(
            server_id="test_server_mixed",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_server)
        await db.flush()

        # Player 1: No sessions
        player1 = Player(
            uuid="uuid-no-sessions",
            current_name="Player1NoSessions",
            created_at=datetime.now(timezone.utc),
        )
        db.add(player1)

        # Player 2: Offline session
        player2 = Player(
            uuid="uuid-offline",
            current_name="Player2Offline",
            created_at=datetime.now(timezone.utc),
        )
        db.add(player2)
        await db.flush()

        left_time = datetime.now(timezone.utc) - timedelta(hours=1)
        session2 = PlayerSession(
            player_db_id=player2.player_db_id,
            server_db_id=test_server.id,
            joined_at=left_time - timedelta(hours=2),
            left_at=left_time,
            duration_seconds=7200,
        )
        db.add(session2)

        # Player 3: Online session
        player3 = Player(
            uuid="uuid-online",
            current_name="Player3Online",
            created_at=datetime.now(timezone.utc),
        )
        db.add(player3)
        await db.flush()

        session3 = PlayerSession(
            player_db_id=player3.player_db_id,
            server_db_id=test_server.id,
            joined_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            left_at=None,
            duration_seconds=None,
        )
        db.add(session3)

        await db.commit()

        # Get all player summaries
        players_summary = await get_all_players_summary(db)

        # Verify Player 1 (no sessions)
        summary1 = next(
            (p for p in players_summary if p.uuid == "uuid-no-sessions"), None
        )
        assert summary1 is not None
        assert summary1.last_seen is None, "Player1 should have last_seen=NULL"
        assert summary1.is_online is False
        assert summary1.total_playtime_seconds == 0

        # Verify Player 2 (offline)
        summary2 = next((p for p in players_summary if p.uuid == "uuid-offline"), None)
        assert summary2 is not None
        assert summary2.last_seen is not None
        assert abs((summary2.last_seen - left_time).total_seconds()) < 1
        assert summary2.is_online is False
        assert summary2.total_playtime_seconds == 7200

        # Verify Player 3 (online)
        summary3 = next((p for p in players_summary if p.uuid == "uuid-online"), None)
        assert summary3 is not None
        assert summary3.last_seen is not None
        now = datetime.now(timezone.utc)
        assert abs((summary3.last_seen - now).total_seconds()) < 2
        assert summary3.is_online is True

        print("✓ All three player states handled correctly in single query")

    finally:
        await cleanup_test_db(db, engine, temp_db_path)
