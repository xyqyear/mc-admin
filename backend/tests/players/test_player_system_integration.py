"""
Integration tests for player management system.

Tests complete event flows without mocking internal logic.
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
from app.events.base import (
    PlayerAchievementEvent,
    PlayerChatMessageEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from app.models import (
    Player,
    PlayerAchievement,
    PlayerChatMessage,
    PlayerSession,
    Server,
    ServerStatus,
)
from app.players import ChatTracker, PlayerManager, SessionTracker
from app.players.skin_fetcher import SkinFetcher

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
def clean_dispatcher():
    """Clean event dispatcher handlers before and after test."""
    from app.events import event_dispatcher

    # Save current handlers
    saved = {k: list(v) for k, v in event_dispatcher._handlers.items()}

    # Clear all handlers
    for handlers in event_dispatcher._handlers.values():
        handlers.clear()

    yield event_dispatcher

    # Restore handlers
    event_dispatcher._handlers = saved


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
async def player_system(
    test_database, clean_dispatcher, mock_skin_fetcher, mock_mojang_api
):
    """Initialize complete player system with mocked external dependencies."""

    # Patch all database sessions and external APIs
    # Need to patch at all import points because imports happen before patching
    patches = [
        patch("app.db.database.get_async_session", test_database),
        patch("app.players.player_manager.get_async_session", test_database),
        patch("app.players.session_tracker.get_async_session", test_database),
        patch("app.players.chat_tracker.get_async_session", test_database),
        patch("app.server_tracker.tracker.get_async_session", test_database),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ]

    # Apply all patches
    for p in patches:
        p.start()

    try:
        # Initialize system components
        player_manager = PlayerManager(event_dispatcher=clean_dispatcher)
        session_tracker = SessionTracker(event_dispatcher=clean_dispatcher)
        chat_tracker = ChatTracker(event_dispatcher=clean_dispatcher)

        yield {
            "dispatcher": clean_dispatcher,
            "db": test_database,
            "player_manager": player_manager,
            "session_tracker": session_tracker,
            "chat_tracker": chat_tracker,
        }
    finally:
        # Stop all patches
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
    """Test normal flow: UUID discovered → player joins → player leaves."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    # Create server
    server_db_id = await create_server(db, "server1")

    # Event sequence: UUID → Join → Leave
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="abc123"
        )
    )

    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve")
    )

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
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(server_id="server1", player_name="Steve")
    )

    # Verify player is offline
    assert await is_player_online(db, player.player_db_id, server_db_id) is False

    session = await get_open_session(db, player.player_db_id, server_db_id)
    assert session is None


@pytest.mark.asyncio
async def test_server_stopping_marks_all_offline(player_system):
    """Test server stopping marks all players offline."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # Three players join
    for name in ["Steve", "Alex", "Bob"]:
        await dispatcher.dispatch_player_uuid_discovered(
            PlayerUuidDiscoveredEvent(
                server_id="server1", player_name=name, uuid=f"uuid_{name}"
            )
        )
        await dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(server_id="server1", player_name=name)
        )

    # Verify all online
    for name in ["Steve", "Alex", "Bob"]:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is True

    # Server stops
    await dispatcher.dispatch_server_stopping(ServerStoppingEvent(server_id="server1"))

    # Verify all offline
    for name in ["Steve", "Alex", "Bob"]:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is False


@pytest.mark.asyncio
async def test_missing_uuid_auto_fetch_from_mojang(player_system):
    """Test player joins without UUID - auto fetch from Mojang."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # Player joins WITHOUT UUID discovery event
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve")
    )

    # Should auto-fetch UUID from Mojang
    await asyncio.sleep(0.3)  # Wait for async Mojang call

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
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # Player joins
    join_time = datetime.now(timezone.utc)
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=join_time)
    )

    player = await get_player(db, "Steve")

    # Wait and leave (simulate 5 minutes)
    leave_time = join_time + timedelta(minutes=5)
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(server_id="server1", player_name="Steve", timestamp=leave_time)
    )

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
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    # Session 1: 3 minutes
    t1 = datetime.now(timezone.utc)
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=t1)
    )
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(
            server_id="server1",
            player_name="Steve",
            timestamp=t1 + timedelta(minutes=3),
        )
    )

    # Session 2: 7 minutes
    t2 = t1 + timedelta(minutes=10)
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=t2)
    )
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(
            server_id="server1",
            player_name="Steve",
            timestamp=t2 + timedelta(minutes=7),
        )
    )

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
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # Two players join
    join_time = datetime.now(timezone.utc)
    for name in ["Steve", "Alex"]:
        await dispatcher.dispatch_player_uuid_discovered(
            PlayerUuidDiscoveredEvent(
                server_id="server1", player_name=name, uuid=f"uuid_{name}"
            )
        )
        await dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(
                server_id="server1", player_name=name, timestamp=join_time
            )
        )

    # Server stops after 10 minutes
    stop_time = join_time + timedelta(minutes=10)
    await dispatcher.dispatch_server_stopping(
        ServerStoppingEvent(server_id="server1", timestamp=stop_time)
    )

    # Check both sessions ended
    for name in ["Steve", "Alex"]:
        player = await get_player(db, name)
        session = await get_open_session(db, player.player_db_id, server_db_id)
        assert session is None

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
    dispatcher = player_system["dispatcher"]

    await create_server(db, "server1")

    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve")
    )

    player = await get_player(db, "Steve")

    # Send chat messages
    messages = ["Hello world", "How are you?", "Goodbye"]
    for msg in messages:
        await dispatcher.dispatch_player_chat_message(
            PlayerChatMessageEvent(
                server_id="server1", player_name="Steve", message=msg
            )
        )

    # Verify messages
    chat_msgs = await get_chat_messages(db, player.player_db_id)
    assert len(chat_msgs) == 3
    assert [m.message_text for m in chat_msgs] == messages


@pytest.mark.asyncio
async def test_achievements_recorded_and_deduplicated(player_system):
    """Test achievements are recorded and deduplicated."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    await create_server(db, "server1")

    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    player = await get_player(db, "Steve")

    # Earn achievements
    await dispatcher.dispatch_player_achievement(
        PlayerAchievementEvent(
            server_id="server1",
            player_name="Steve",
            achievement_name="Taking Inventory",
        )
    )
    await dispatcher.dispatch_player_achievement(
        PlayerAchievementEvent(
            server_id="server1",
            player_name="Steve",
            achievement_name="Getting Wood",
        )
    )

    # Duplicate achievement (should be ignored)
    await dispatcher.dispatch_player_achievement(
        PlayerAchievementEvent(
            server_id="server1",
            player_name="Steve",
            achievement_name="Taking Inventory",
        )
    )

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
    """Test player leave event without prior join - should handle gracefully."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    await create_server(db, "server1")

    # Player leaves without joining (edge case)
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(server_id="server1", player_name="Steve")
    )

    # Should not crash, player might be fetched from Mojang
    await asyncio.sleep(0.3)

    player = await get_player(db, "Steve")
    # Player should exist from Mojang fetch
    assert player is not None


@pytest.mark.asyncio
async def test_uuid_update_for_existing_player(player_system):
    """Test UUID discovery with same UUID updates player name."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    await create_server(db, "server1")

    # Discover UUID from logs (creates player with name Steve)
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="consistent_uuid_123"
        )
    )

    await asyncio.sleep(0.1)
    player = await get_player(db, "Steve")
    assert player.uuid == "consistent_uuid_123"
    assert player.current_name == "Steve"

    # Player changes name to Steve2 (UUID stays same - this is what actually happens in Minecraft)
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve2", uuid="consistent_uuid_123"
        )
    )

    await asyncio.sleep(0.1)
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
    dispatcher = player_system["dispatcher"]

    server1_id = await create_server(db, "server1")
    server2_id = await create_server(db, "server2")

    # Player joins server1
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve")
    )

    # Same player joins server2
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server2", player_name="Steve")
    )

    player = await get_player(db, "Steve")

    # Check online on both servers
    assert await is_player_online(db, player.player_db_id, server1_id) is True
    assert await is_player_online(db, player.player_db_id, server2_id) is True

    # Leave server1, should still be online on server2
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(server_id="server1", player_name="Steve")
    )

    assert await is_player_online(db, player.player_db_id, server1_id) is False
    assert await is_player_online(db, player.player_db_id, server2_id) is True


@pytest.mark.asyncio
async def test_rapid_join_leave_cycles(player_system):
    """Test rapid join/leave cycles."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    player = await get_player(db, "Steve")

    # 5 rapid join/leave cycles
    base_time = datetime.now(timezone.utc)
    for i in range(5):
        join_time = base_time + timedelta(minutes=i * 2)
        leave_time = join_time + timedelta(minutes=1)

        await dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(
                server_id="server1", player_name="Steve", timestamp=join_time
            )
        )
        await dispatcher.dispatch_player_left(
            PlayerLeftEvent(
                server_id="server1", player_name="Steve", timestamp=leave_time
            )
        )

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
        for session in sessions:
            assert session.duration_seconds == 60


@pytest.mark.asyncio
async def test_concurrent_players_on_same_server(player_system):
    """Test multiple players on same server concurrently."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    players = ["Steve", "Alex", "Bob", "Alice", "Charlie"]

    # All players join
    for name in players:
        await dispatcher.dispatch_player_uuid_discovered(
            PlayerUuidDiscoveredEvent(
                server_id="server1", player_name=name, uuid=f"uuid_{name}"
            )
        )
        await dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(server_id="server1", player_name=name)
        )

    # Verify all online
    for name in players:
        player = await get_player(db, name)
        assert await is_player_online(db, player.player_db_id, server_db_id) is True

    # Some players leave
    for name in ["Steve", "Bob"]:
        await dispatcher.dispatch_player_left(
            PlayerLeftEvent(server_id="server1", player_name=name)
        )

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
    dispatcher = player_system["dispatcher"]

    await create_server(db, "server1")

    # Different case variations should be treated as different players
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid_lower"
        )
    )
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="STEVE", uuid="uuid_upper"
        )
    )

    player_lower = await get_player(db, "Steve")
    player_upper = await get_player(db, "STEVE")

    assert player_lower is not None
    assert player_upper is not None
    assert player_lower.player_db_id != player_upper.player_db_id
    assert player_lower.uuid == "uuid_lower"
    assert player_upper.uuid == "uuid_upper"


@pytest.mark.asyncio
async def test_player_last_seen_update(player_system):
    """Test player last_seen timestamp is updated on join."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    await create_server(db, "server1")

    # First join
    time1 = datetime.now(timezone.utc)
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=time1)
    )

    player = await get_player(db, "Steve")
    assert player.last_seen is not None
    first_seen = player.last_seen

    # Leave and rejoin later
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(server_id="server1", player_name="Steve", timestamp=time1)
    )

    time2 = time1 + timedelta(hours=1)
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=time2)
    )

    player = await get_player(db, "Steve")
    assert player.last_seen > first_seen


@pytest.mark.asyncio
async def test_achievement_same_name_different_servers(player_system):
    """Test same achievement on different servers are separate records."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server1_id = await create_server(db, "server1")
    server2_id = await create_server(db, "server2")

    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    player = await get_player(db, "Steve")

    # Same achievement on server1
    await dispatcher.dispatch_player_achievement(
        PlayerAchievementEvent(
            server_id="server1",
            player_name="Steve",
            achievement_name="Taking Inventory",
        )
    )

    # Same achievement on server2
    await dispatcher.dispatch_player_achievement(
        PlayerAchievementEvent(
            server_id="server2",
            player_name="Steve",
            achievement_name="Taking Inventory",
        )
    )

    # Should have 2 achievement records
    achievements = await get_achievements(db, player.player_db_id)
    assert len(achievements) == 2

    server_ids = [a.server_db_id for a in achievements]
    assert server1_id in server_ids
    assert server2_id in server_ids
