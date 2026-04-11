"""
Integration tests for player management system.

Tests complete tracking flows using direct function calls.
Only mocks: skin_fetcher, mojang_api, and uses isolated test databases.
"""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base
from app.models import (
    Player,
    PlayerAchievement,
    PlayerChatMessage,
    PlayerSession,
    Server,
    ServerStatus,
)
from app.players.crud import upsert_player
from app.players.skin_fetcher import SkinFetcher
from app.players.tracking import (
    close_server_sessions,
    process_player_join,
    process_player_left,
    record_achievement,
    record_chat_message,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def test_database():
    """Create isolated test database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    @asynccontextmanager
    async def get_session():
        async with async_session_maker() as session:
            yield session

    yield get_session

    await engine.dispose()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def mock_skin_fetcher():
    """Mock skin fetcher with 200ms network delay."""

    async def fetch_skin(uuid: str):
        await asyncio.sleep(0.2)
        return (b"skin_data_" + uuid.encode(), b"avatar_data_" + uuid.encode())

    return AsyncMock(side_effect=fetch_skin)


@pytest.fixture
def mock_mojang_api():
    """Mock Mojang API with 200ms network delay."""

    async def fetch_uuid(player_name: str):
        await asyncio.sleep(0.2)
        # Return consistent UUID based on name
        import hashlib

        hash_hex = hashlib.md5(player_name.encode()).hexdigest()
        return hash_hex[:32]  # 32 chars without dashes

    return AsyncMock(side_effect=fetch_uuid)


@pytest.fixture
async def player_system(test_database, mock_skin_fetcher, mock_mojang_api):
    """Initialize player system with mocked external dependencies."""

    patches = [
        patch("app.players.tracking.get_async_session", test_database),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch("app.players.crud.player.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ]

    for p in patches:
        p.start()

    try:
        yield {
            "db": test_database,
        }
    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Helper Functions
# ============================================================================


async def create_server(db, server_id: str) -> int:
    """Create server in database and return server database id."""
    async with db() as session:
        now = datetime.now(timezone.utc)
        server = Server(
            server_id=server_id,
            status=ServerStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)
        return server.id


async def get_player(db, player_name: str):
    """Get player by name."""
    async with db() as session:
        result = await session.execute(
            select(Player).where(Player.current_name == player_name)
        )
        return result.scalar_one_or_none()


async def is_player_online(db, player_db_id: int, server_db_id: int) -> bool:
    """Check if player is online (has open session)."""
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player_db_id,
                PlayerSession.server_db_id == server_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        return result.scalar_one_or_none() is not None


async def get_open_session(db, player_db_id: int, server_db_id: int):
    """Get open session."""
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player_db_id,
                PlayerSession.server_db_id == server_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


async def get_chat_messages(db, player_db_id: int):
    """Get player chat messages."""
    async with db() as session:
        result = await session.execute(
            select(PlayerChatMessage)
            .where(PlayerChatMessage.player_db_id == player_db_id)
            .order_by(PlayerChatMessage.sent_at)
        )
        return list(result.scalars().all())


async def get_achievements(db, player_db_id: int):
    """Get player achievements."""
    async with db() as session:
        result = await session.execute(
            select(PlayerAchievement)
            .where(PlayerAchievement.player_db_id == player_db_id)
            .order_by(PlayerAchievement.earned_at)
        )
        return list(result.scalars().all())


# ============================================================================
# Test Cases - Basic Flows
# ============================================================================


@pytest.mark.asyncio
async def test_normal_flow_uuid_join_leave(player_system):
    """Test normal flow: UUID upserted -> player joins -> player leaves."""
    db = player_system["db"]

    # Create server
    server_db_id = await create_server(db, "server1")

    # Upsert player UUID directly
    async with db() as session:
        await upsert_player(session, "abc123", "Steve")

    # Player joins
    await process_player_join("server1", "Steve")

    # Verify player is online
    player = await get_player(db, "Steve")
    assert player is not None
    assert player.uuid == "abc123"
    assert player.current_name == "Steve"

    # Check player is online (has open session)
    assert await is_player_online(db, player.player_db_id, server_db_id) is True

    session = await get_open_session(db, player.player_db_id, server_db_id)
    assert session is not None

    # Player leaves
    await process_player_left("server1", "Steve")

    # Verify player is offline
    assert await is_player_online(db, player.player_db_id, server_db_id) is False

    session = await get_open_session(db, player.player_db_id, server_db_id)
    assert session is None


@pytest.mark.asyncio
async def test_server_stopping_marks_all_offline(player_system):
    """Test server stopping marks all players offline."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    # Three players: upsert UUID then join
    for name in ["Steve", "Alex", "Bob"]:
        async with db() as session:
            await upsert_player(session, f"uuid_{name}", name)
        await process_player_join("server1", name)

    # Verify all online
    for name in ["Steve", "Alex", "Bob"]:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is True

    # Server stops
    await close_server_sessions("server1")

    # Verify all offline
    for name in ["Steve", "Alex", "Bob"]:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is False


@pytest.mark.asyncio
async def test_missing_uuid_auto_fetch_from_mojang(player_system):
    """Test player joins without UUID - auto fetch from Mojang."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    # Player joins WITHOUT prior UUID upsert - should auto-fetch from Mojang
    await process_player_join("server1", "Steve")

    player = await get_player(db, "Steve")
    assert player is not None
    assert player.uuid is not None  # Should have UUID from Mojang mock
    assert len(player.uuid) == 32  # MD5 hash length

    assert await is_player_online(db, player.player_db_id, server_db_id) is True


# ============================================================================
# Test Cases - Session and Playtime
# ============================================================================


@pytest.mark.asyncio
async def test_session_duration_calculation(player_system):
    """Test session duration and playtime calculation."""
    db = player_system["db"]

    await create_server(db, "server1")

    # Upsert player UUID
    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    # Player joins
    join_time = datetime.now(timezone.utc)
    await process_player_join("server1", "Steve", timestamp=join_time)

    player = await get_player(db, "Steve")

    # Player leaves after 5 minutes
    leave_time = join_time + timedelta(minutes=5)
    await process_player_left("server1", "Steve", timestamp=leave_time)

    # Check session duration
    async with db() as session:
        result = await session.execute(
            select(PlayerSession)
            .where(PlayerSession.player_db_id == player.player_db_id)
            .order_by(PlayerSession.joined_at.desc())
        )
        player_session = result.scalar_one()
        assert player_session.duration_seconds == 300  # 5 minutes


@pytest.mark.asyncio
async def test_multiple_sessions_recorded(player_system):
    """Test multiple sessions are recorded correctly."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    # Session 1: 3 minutes
    t1 = datetime.now(timezone.utc)
    await process_player_join("server1", "Steve", timestamp=t1)
    await process_player_left("server1", "Steve", timestamp=t1 + timedelta(minutes=3))

    # Session 2: 7 minutes
    t2 = t1 + timedelta(minutes=10)
    await process_player_join("server1", "Steve", timestamp=t2)
    await process_player_left("server1", "Steve", timestamp=t2 + timedelta(minutes=7))

    # Verify both sessions were recorded
    player = await get_player(db, "Steve")
    async with db() as session:
        result = await session.execute(
            select(PlayerSession)
            .where(
                PlayerSession.player_db_id == player.player_db_id,
                PlayerSession.server_db_id == server_db_id,
            )
            .order_by(PlayerSession.joined_at)
        )
        sessions = list(result.scalars().all())
        assert len(sessions) == 2
        assert sessions[0].duration_seconds == 180  # 3 minutes
        assert sessions[1].duration_seconds == 420  # 7 minutes


@pytest.mark.asyncio
async def test_server_stop_ends_sessions(player_system):
    """Test server stop ends all open sessions with correct duration."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    # Two players join
    join_time = datetime.now(timezone.utc)
    for name in ["Steve", "Alex"]:
        async with db() as session:
            await upsert_player(session, f"uuid_{name}", name)
        await process_player_join("server1", name, timestamp=join_time)

    # Server stops after 10 minutes
    stop_time = join_time + timedelta(minutes=10)
    await close_server_sessions("server1", timestamp=stop_time)

    # Check both sessions ended
    for name in ["Steve", "Alex"]:
        player = await get_player(db, name)
        open_session = await get_open_session(db, player.player_db_id, server_db_id)
        assert open_session is None

        # Check session was recorded with correct duration
        async with db() as session:
            result = await session.execute(
                select(PlayerSession)
                .where(
                    PlayerSession.player_db_id == player.player_db_id,
                    PlayerSession.server_db_id == server_db_id,
                )
                .order_by(PlayerSession.joined_at.desc())
            )
            player_session = result.scalar_one()
            assert player_session.duration_seconds == 600  # 10 minutes


# ============================================================================
# Test Cases - Chat and Achievements
# ============================================================================


@pytest.mark.asyncio
async def test_chat_messages_recorded(player_system):
    """Test chat messages are recorded."""
    db = player_system["db"]

    await create_server(db, "server1")

    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    await process_player_join("server1", "Steve")

    player = await get_player(db, "Steve")

    # Send chat messages
    messages = ["Hello world", "How are you?", "Goodbye"]
    for msg in messages:
        await record_chat_message("server1", "Steve", msg)

    # Verify messages
    chat_msgs = await get_chat_messages(db, player.player_db_id)
    assert len(chat_msgs) == 3
    assert [m.message_text for m in chat_msgs] == messages


@pytest.mark.asyncio
async def test_achievements_recorded_and_deduplicated(player_system):
    """Test achievements are recorded and deduplicated."""
    db = player_system["db"]

    await create_server(db, "server1")

    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    player = await get_player(db, "Steve")

    # Earn achievements (player_name arg is the achievement text to match against)
    await record_achievement("server1", "Steve", "Taking Inventory")
    await record_achievement("server1", "Steve", "Getting Wood")

    # Duplicate achievement (should be ignored)
    await record_achievement("server1", "Steve", "Taking Inventory")

    # Verify achievements (no duplicates)
    achievements = await get_achievements(db, player.player_db_id)
    assert len(achievements) == 2
    achievement_names = [a.achievement_name for a in achievements]
    assert "Taking Inventory" in achievement_names
    assert "Getting Wood" in achievement_names


# ============================================================================
# Test Cases - Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_player_leave_without_join(player_system):
    """Test player leave without prior join - should handle gracefully."""
    db = player_system["db"]

    await create_server(db, "server1")

    # Player leaves without joining (edge case)
    await process_player_left("server1", "Steve")

    # Should not crash, player should be fetched from Mojang
    player = await get_player(db, "Steve")
    assert player is not None


@pytest.mark.asyncio
async def test_uuid_update_for_existing_player(player_system):
    """Test UUID upsert with same UUID updates player name."""
    db = player_system["db"]

    await create_server(db, "server1")

    # Upsert player with name Steve
    async with db() as session:
        await upsert_player(session, "consistent_uuid_123", "Steve")

    player = await get_player(db, "Steve")
    assert player.uuid == "consistent_uuid_123"
    assert player.current_name == "Steve"

    # Player changes name to Steve2 (UUID stays same)
    async with db() as session:
        await upsert_player(session, "consistent_uuid_123", "Steve2")

    # Query the player by UUID
    async with db() as session:
        result = await session.execute(
            select(Player).where(Player.uuid == "consistent_uuid_123")
        )
        player = result.scalar_one()

    # Name should be updated to Steve2
    assert player.current_name == "Steve2"
    assert player.uuid == "consistent_uuid_123"


@pytest.mark.asyncio
async def test_multiple_servers_same_player(player_system):
    """Test same player on multiple servers."""
    db = player_system["db"]

    server1_id = await create_server(db, "server1")
    server2_id = await create_server(db, "server2")

    # Upsert player UUID
    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    # Player joins server1
    await process_player_join("server1", "Steve")

    # Same player joins server2
    await process_player_join("server2", "Steve")

    player = await get_player(db, "Steve")

    # Check online on both servers
    assert await is_player_online(db, player.player_db_id, server1_id) is True
    assert await is_player_online(db, player.player_db_id, server2_id) is True

    # Leave server1, should still be online on server2
    await process_player_left("server1", "Steve")

    assert await is_player_online(db, player.player_db_id, server1_id) is False
    assert await is_player_online(db, player.player_db_id, server2_id) is True


@pytest.mark.asyncio
async def test_rapid_join_leave_cycles(player_system):
    """Test rapid join/leave cycles."""
    db = player_system["db"]

    await create_server(db, "server1")

    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    player = await get_player(db, "Steve")

    # 5 rapid join/leave cycles
    base_time = datetime.now(timezone.utc)
    for i in range(5):
        join_time = base_time + timedelta(minutes=i * 2)
        leave_time = join_time + timedelta(minutes=1)

        await process_player_join("server1", "Steve", timestamp=join_time)
        await process_player_left("server1", "Steve", timestamp=leave_time)

    # Check session count
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player.player_db_id
            )
        )
        sessions = list(result.scalars().all())
        assert len(sessions) == 5
        # Verify each session has 1 minute (60 seconds) duration
        for s in sessions:
            assert s.duration_seconds == 60


@pytest.mark.asyncio
async def test_concurrent_players_on_same_server(player_system):
    """Test multiple players on same server concurrently."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    players = ["Steve", "Alex", "Bob", "Alice", "Charlie"]

    # All players join
    for name in players:
        async with db() as session:
            await upsert_player(session, f"uuid_{name}", name)
        await process_player_join("server1", name)

    # Verify all online
    for name in players:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is True

    # Some players leave
    for name in ["Steve", "Bob"]:
        await process_player_left("server1", name)

    # Verify correct online status
    online_players = ["Alex", "Alice", "Charlie"]
    offline_players = ["Steve", "Bob"]

    for name in online_players:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is True

    for name in offline_players:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is False


@pytest.mark.asyncio
async def test_player_name_case_sensitivity(player_system):
    """Test player names are case-sensitive."""
    db = player_system["db"]

    await create_server(db, "server1")

    # Different case variations should be treated as different players
    async with db() as session:
        await upsert_player(session, "uuid_lower", "Steve")

    async with db() as session:
        await upsert_player(session, "uuid_upper", "STEVE")

    player_lower = await get_player(db, "Steve")
    player_upper = await get_player(db, "STEVE")

    assert player_lower is not None
    assert player_upper is not None
    assert player_lower.player_db_id != player_upper.player_db_id
    assert player_lower.uuid == "uuid_lower"
    assert player_upper.uuid == "uuid_upper"


@pytest.mark.asyncio
async def test_player_last_seen_update(player_system):
    """Test player last_seen timestamp is calculated correctly from sessions."""
    from app.players.crud.query.player_query import get_player_last_seen

    db = player_system["db"]

    await create_server(db, "server1")

    # Upsert UUID and join
    time1 = datetime.now(timezone.utc)
    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    await process_player_join("server1", "Steve", timestamp=time1)

    player = await get_player(db, "Steve")
    async with db() as session:
        first_last_seen = await get_player_last_seen(session, player.player_db_id)
    assert first_last_seen is not None
    # Player is online, so last_seen should be very recent (close to now)
    assert (datetime.now(timezone.utc) - first_last_seen).total_seconds() < 5

    # Leave 30 minutes later (realistic session duration)
    leave_time = time1 + timedelta(minutes=30)
    await process_player_left("server1", "Steve", timestamp=leave_time)

    # After leaving, last_seen should be the left_at time
    async with db() as session:
        second_last_seen = await get_player_last_seen(session, player.player_db_id)
    assert second_last_seen is not None
    assert abs((second_last_seen - leave_time).total_seconds()) < 1

    # Rejoin later
    time2 = time1 + timedelta(hours=1)
    await process_player_join("server1", "Steve", timestamp=time2)

    # Player is online again, last_seen should be current time
    async with db() as session:
        third_last_seen = await get_player_last_seen(session, player.player_db_id)
    assert third_last_seen is not None
    assert (datetime.now(timezone.utc) - third_last_seen).total_seconds() < 5


@pytest.mark.asyncio
async def test_achievement_same_name_different_servers(player_system):
    """Test same achievement on different servers are separate records."""
    db = player_system["db"]

    server1_id = await create_server(db, "server1")
    server2_id = await create_server(db, "server2")

    async with db() as session:
        await upsert_player(session, "uuid1", "Steve")

    player = await get_player(db, "Steve")

    # Same achievement on server1
    await record_achievement("server1", "Steve", "Taking Inventory")

    # Same achievement on server2
    await record_achievement("server2", "Steve", "Taking Inventory")

    # Should have 2 achievement records
    achievements = await get_achievements(db, player.player_db_id)
    assert len(achievements) == 2

    server_ids = [a.server_db_id for a in achievements]
    assert server1_id in server_ids
    assert server2_id in server_ids
