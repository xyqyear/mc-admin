"""Test playtime calculation including ongoing sessions."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Player, PlayerSession, Server
from app.players.crud.query.player_query import (
    get_all_players_summary,
    get_player_detail_by_uuid,
)


async def create_test_db():
    """Create a temporary test database and return session."""
    # Create temporary database file
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db_path = Path(temp_db.name)
    temp_db.close()

    # Create async engine for test database
    database_url = f"sqlite+aiosqlite:///{temp_db_path}"
    engine = create_async_engine(database_url, echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create session
    session = async_session()

    return session, engine, temp_db_path


async def cleanup_test_db(session, engine, temp_db_path):
    """Cleanup test database."""
    await session.close()
    await engine.dispose()
    temp_db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_playtime_with_finished_and_ongoing_sessions():
    """Test that total playtime includes both finished and ongoing sessions.

    This test verifies:
    1. Finished sessions use duration_seconds directly
    2. Ongoing sessions calculate duration from joined_at to now
    3. Total playtime is the sum of both
    """
    db, engine, temp_db_path = await create_test_db()

    try:
        test_player_uuid = "test-uuid-playtime-123"
        test_server_id = "test_server_playtime"

        # Create test server
        test_server = Server(
            server_id=test_server_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_server)
        await db.flush()

        # Create test player
        test_player = Player(
            uuid=test_player_uuid,
            current_name="TestPlayer",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_player)
        await db.flush()

        # Create finished sessions
        # Session 1: 1 hour ago, played for 3600 seconds (1 hour)
        session1_joined = datetime.now(timezone.utc) - timedelta(hours=2)
        session1_left = session1_joined + timedelta(hours=1)
        session1 = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=session1_joined,
            left_at=session1_left,
            duration_seconds=3600,
        )
        db.add(session1)

        # Session 2: 30 minutes ago, played for 1800 seconds (30 minutes)
        session2_joined = datetime.now(timezone.utc) - timedelta(minutes=60)
        session2_left = session2_joined + timedelta(minutes=30)
        session2 = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=session2_joined,
            left_at=session2_left,
            duration_seconds=1800,
        )
        db.add(session2)

        # Create ongoing session (no left_at, no duration_seconds)
        # Joined 10 minutes ago, still playing
        ongoing_joined = datetime.now(timezone.utc) - timedelta(minutes=10)
        session3 = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=ongoing_joined,
            left_at=None,
            duration_seconds=None,
        )
        db.add(session3)

        await db.commit()

        # Test get_all_players_summary
        players_summary = await get_all_players_summary(db)

        # Find our test player
        test_player_summary = next(
            (p for p in players_summary if p.uuid == test_player_uuid), None
        )
        assert test_player_summary is not None, "Test player not found in summary"

        # Expected playtime:
        # - Session 1: 3600 seconds (1 hour)
        # - Session 2: 1800 seconds (30 minutes)
        # - Session 3 (ongoing): ~600 seconds (10 minutes, may vary slightly)
        # Total: ~5400 seconds (90 minutes)
        expected_min = 3600 + 1800 + 580  # Allow some tolerance for timing
        expected_max = 3600 + 1800 + 620

        assert (
            expected_min <= test_player_summary.total_playtime_seconds <= expected_max
        ), (
            f"Total playtime {test_player_summary.total_playtime_seconds} "
            f"not in expected range [{expected_min}, {expected_max}]"
        )

        print(
            f"✓ Player summary playtime: {test_player_summary.total_playtime_seconds} seconds "
            f"(expected ~5400, range: {expected_min}-{expected_max})"
        )

        # Test get_player_detail_by_uuid
        player_detail = await get_player_detail_by_uuid(db, test_player_uuid)
        assert player_detail is not None, "Player detail not found"

        assert expected_min <= player_detail.total_playtime_seconds <= expected_max, (
            f"Total playtime {player_detail.total_playtime_seconds} "
            f"not in expected range [{expected_min}, {expected_max}]"
        )

        print(
            f"✓ Player detail playtime: {player_detail.total_playtime_seconds} seconds "
            f"(expected ~5400, range: {expected_min}-{expected_max})"
        )

        # Verify player is marked as online (has ongoing session)
        assert player_detail.is_online is True, "Player should be online"
        assert test_server_id in player_detail.current_servers, (
            f"Player should be on {test_server_id}"
        )

        print("✓ Player correctly marked as online")

    finally:
        await cleanup_test_db(db, engine, temp_db_path)


@pytest.mark.asyncio
async def test_playtime_with_only_ongoing_sessions():
    """Test playtime calculation with only ongoing sessions (no finished sessions)."""
    db, engine, temp_db_path = await create_test_db()

    try:
        test_player_uuid = "test-uuid-ongoing-456"
        test_server_id = "test_server_ongoing"

        # Create test server
        test_server = Server(
            server_id=test_server_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_server)
        await db.flush()

        # Create test player
        test_player = Player(
            uuid=test_player_uuid,
            current_name="OngoingPlayer",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_player)
        await db.flush()

        # Create only ongoing session
        # Joined 5 minutes ago
        ongoing_joined = datetime.now(timezone.utc) - timedelta(minutes=5)
        session = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=ongoing_joined,
            left_at=None,
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

        # Expected: ~300 seconds (5 minutes)
        expected_min = 280
        expected_max = 320

        assert (
            expected_min <= test_player_summary.total_playtime_seconds <= expected_max
        ), (
            f"Total playtime {test_player_summary.total_playtime_seconds} "
            f"not in expected range [{expected_min}, {expected_max}]"
        )

        print(
            f"✓ Ongoing-only playtime: {test_player_summary.total_playtime_seconds} seconds "
            f"(expected ~300, range: {expected_min}-{expected_max})"
        )

    finally:
        await cleanup_test_db(db, engine, temp_db_path)


@pytest.mark.asyncio
async def test_playtime_with_only_finished_sessions():
    """Test playtime calculation with only finished sessions (no ongoing sessions)."""
    db, engine, temp_db_path = await create_test_db()

    try:
        test_player_uuid = "test-uuid-finished-789"
        test_server_id = "test_server_finished"

        # Create test server
        test_server = Server(
            server_id=test_server_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_server)
        await db.flush()

        # Create test player
        test_player = Player(
            uuid=test_player_uuid,
            current_name="FinishedPlayer",
            created_at=datetime.now(timezone.utc),
        )
        db.add(test_player)
        await db.flush()

        # Create only finished sessions
        session1_joined = datetime.now(timezone.utc) - timedelta(hours=3)
        session1_left = session1_joined + timedelta(hours=2)
        session1 = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=session1_joined,
            left_at=session1_left,
            duration_seconds=7200,  # 2 hours
        )
        db.add(session1)
        await db.commit()

        # Get player summary
        players_summary = await get_all_players_summary(db)
        test_player_summary = next(
            (p for p in players_summary if p.uuid == test_player_uuid),
            None,
        )

        assert test_player_summary is not None
        assert test_player_summary.total_playtime_seconds == 7200, (
            f"Expected 7200 seconds, got {test_player_summary.total_playtime_seconds}"
        )

        # Player should be offline
        assert test_player_summary.is_online is False, "Player should be offline"

        print(
            f"✓ Finished-only playtime: {test_player_summary.total_playtime_seconds} seconds "
            f"(expected exactly 7200)"
        )

    finally:
        await cleanup_test_db(db, engine, temp_db_path)
