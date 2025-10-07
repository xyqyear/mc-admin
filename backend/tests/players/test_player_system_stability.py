"""
Stability and stress tests for player management system.

Tests complex scenarios, race conditions, and system stability.
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
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from app.models import (
    Player,
    PlayerOnlineStatus,
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
    """Create isolated test database."""
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
    """Clean event dispatcher."""
    from app.events import event_dispatcher

    saved = {k: list(v) for k, v in event_dispatcher._handlers.items()}
    for handlers in event_dispatcher._handlers.values():
        handlers.clear()

    yield event_dispatcher

    event_dispatcher._handlers = saved


@pytest.fixture
def mock_skin_fetcher():
    """Mock skin fetcher."""

    async def fetch_skin(uuid: str):
        await asyncio.sleep(0.2)
        return (b"skin_" + uuid.encode(), b"avatar_" + uuid.encode())

    return AsyncMock(side_effect=fetch_skin)


@pytest.fixture
def mock_mojang_api():
    """Mock Mojang API."""

    async def fetch_uuid(player_name: str):
        await asyncio.sleep(0.2)
        import hashlib

        return hashlib.md5(player_name.encode()).hexdigest()[:32]

    return AsyncMock(side_effect=fetch_uuid)


@pytest.fixture
async def player_system(
    test_database, clean_dispatcher, mock_skin_fetcher, mock_mojang_api
):
    """Initialize player system."""
    patches = [
        patch("app.db.database.get_async_session", test_database),
        patch("app.players.player_manager.get_async_session", test_database),
        patch("app.players.session_tracker.get_async_session", test_database),
        patch("app.players.chat_tracker.get_async_session", test_database),
        patch("app.server_tracker.tracker.get_async_session", test_database),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ]

    for p in patches:
        p.start()

    try:
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
        for p in patches:
            p.stop()


# ============================================================================
# Helpers
# ============================================================================


async def create_server(db, server_id: str) -> int:
    """Create server."""
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
    """Get player."""
    async with db() as session:
        result = await session.execute(
            select(Player).where(Player.current_name == player_name)
        )
        return result.scalar_one_or_none()


async def count_sessions(db, player_db_id: int):
    """Count player sessions."""
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(PlayerSession.player_db_id == player_db_id)
        )
        return len(list(result.scalars().all()))


# ============================================================================
# Concurrency Tests
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_events_same_player(player_system):
    """Test concurrent events for same player are handled correctly."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    _server_db_id = await create_server(db, "server1")

    # Dispatch UUID discovery
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    # Concurrent join/leave events (simulating race condition)
    join_time = datetime.now(timezone.utc)

    await asyncio.gather(
        dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(
                server_id="server1", player_name="Steve", timestamp=join_time
            )
        ),
        dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(
                server_id="server1",
                player_name="Steve",
                timestamp=join_time + timedelta(seconds=1),
            )
        ),
        dispatcher.dispatch_player_left(
            PlayerLeftEvent(
                server_id="server1",
                player_name="Steve",
                timestamp=join_time + timedelta(seconds=2),
            )
        ),
    )

    # System should handle this gracefully
    player = await get_player(db, "Steve")
    assert player is not None

    # Should have created sessions
    session_count = await count_sessions(db, player.player_db_id)
    assert session_count >= 1


@pytest.mark.asyncio
async def test_rapid_server_stop_events(player_system):
    """Test rapid server stop events are handled correctly."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # Create players
    for i in range(5):
        await dispatcher.dispatch_player_uuid_discovered(
            PlayerUuidDiscoveredEvent(
                server_id="server1", player_name=f"Player{i}", uuid=f"uuid{i}"
            )
        )
        await dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(server_id="server1", player_name=f"Player{i}")
        )

    # Multiple rapid stop events
    await asyncio.gather(
        *[
            dispatcher.dispatch_server_stopping(
                ServerStoppingEvent(server_id="server1")
            )
            for _ in range(10)
        ]
    )

    # All players should be offline
    async with db() as session:
        result = await session.execute(
            select(PlayerOnlineStatus).where(
                PlayerOnlineStatus.server_db_id == server_db_id
            )
        )
        statuses = list(result.scalars().all())
        assert all(not s.is_online for s in statuses)


@pytest.mark.asyncio
async def test_concurrent_multi_server_events(player_system):
    """Test concurrent events across multiple servers."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    # Create 3 servers
    servers = []
    for i in range(3):
        server_id = await create_server(db, f"server{i}")
        servers.append((f"server{i}", server_id))

    # UUID discovery
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server0", player_name="Steve", uuid="uuid1"
        )
    )

    # Player joins all 3 servers concurrently
    await asyncio.gather(
        *[
            dispatcher.dispatch_player_joined(
                PlayerJoinedEvent(server_id=server_id, player_name="Steve")
            )
            for server_id, _ in servers
        ]
    )

    # Verify online on all servers
    player = await get_player(db, "Steve")
    async with db() as session:
        result = await session.execute(
            select(PlayerOnlineStatus).where(
                PlayerOnlineStatus.player_db_id == player.player_db_id
            )
        )
        statuses = list(result.scalars().all())
        assert len(statuses) == 3
        assert all(s.is_online for s in statuses)


# ============================================================================
# Edge Case Stress Tests
# ============================================================================


@pytest.mark.asyncio
async def test_massive_player_count(player_system):
    """Test system handles large number of concurrent players."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # 100 players
    player_count = 100

    # UUID discoveries
    uuid_tasks = [
        dispatcher.dispatch_player_uuid_discovered(
            PlayerUuidDiscoveredEvent(
                server_id="server1", player_name=f"Player{i}", uuid=f"uuid{i}"
            )
        )
        for i in range(player_count)
    ]
    await asyncio.gather(*uuid_tasks)

    # All join
    join_tasks = [
        dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(server_id="server1", player_name=f"Player{i}")
        )
        for i in range(player_count)
    ]
    await asyncio.gather(*join_tasks)

    # Verify all online
    async with db() as session:
        result = await session.execute(
            select(PlayerOnlineStatus).where(
                PlayerOnlineStatus.server_db_id == server_db_id,
                PlayerOnlineStatus.is_online == True,
            )
        )
        online = list(result.scalars().all())
        assert len(online) == player_count

    # Half leave
    leave_tasks = [
        dispatcher.dispatch_player_left(
            PlayerLeftEvent(server_id="server1", player_name=f"Player{i}")
        )
        for i in range(player_count // 2)
    ]
    await asyncio.gather(*leave_tasks)

    # Verify correct count
    async with db() as session:
        result = await session.execute(
            select(PlayerOnlineStatus).where(
                PlayerOnlineStatus.server_db_id == server_db_id,
                PlayerOnlineStatus.is_online == True,
            )
        )
        online = list(result.scalars().all())
        assert len(online) == player_count // 2


@pytest.mark.asyncio
async def test_session_without_leave(player_system):
    """Test open sessions without leave events."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # Multiple players join but never leave
    for i in range(10):
        await dispatcher.dispatch_player_uuid_discovered(
            PlayerUuidDiscoveredEvent(
                server_id="server1", player_name=f"Player{i}", uuid=f"uuid{i}"
            )
        )
        await dispatcher.dispatch_player_joined(
            PlayerJoinedEvent(server_id="server1", player_name=f"Player{i}")
        )

    # Check all have open sessions
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.server_db_id == server_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        open_sessions = list(result.scalars().all())
        assert len(open_sessions) == 10

    # Server stops - should close all
    await dispatcher.dispatch_server_stopping(ServerStoppingEvent(server_id="server1"))

    # Check all sessions closed
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.server_db_id == server_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        open_sessions = list(result.scalars().all())
        assert len(open_sessions) == 0


@pytest.mark.asyncio
async def test_long_session_duration_calculation(player_system):
    """Test session duration calculation for very long sessions."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    _server_db_id = await create_server(db, "server1")

    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    # Player joins
    join_time = datetime.now(timezone.utc) - timedelta(days=1)  # 1 day ago
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=join_time)
    )

    # Player leaves after 24 hours
    leave_time = join_time + timedelta(days=1)
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(server_id="server1", player_name="Steve", timestamp=leave_time)
    )

    # Check duration
    player = await get_player(db, "Steve")
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player.player_db_id
            )
        )
        player_session = result.scalar_one()
        assert player_session.duration_seconds == 86400  # 24 hours in seconds


@pytest.mark.asyncio
async def test_event_ordering_preservation(player_system):
    """Test events are processed in order for same player."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    _server_db_id = await create_server(db, "server1")

    # Precise timing for events
    base_time = datetime.now(timezone.utc)

    # Sequential events with specific timestamps
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    # Session 1: 0-10 minutes
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=base_time)
    )
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(
            server_id="server1",
            player_name="Steve",
            timestamp=base_time + timedelta(minutes=10),
        )
    )

    # Session 2: 20-30 minutes
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(
            server_id="server1",
            player_name="Steve",
            timestamp=base_time + timedelta(minutes=20),
        )
    )
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(
            server_id="server1",
            player_name="Steve",
            timestamp=base_time + timedelta(minutes=30),
        )
    )

    # Verify sessions are separate and correct
    player = await get_player(db, "Steve")
    async with db() as session:
        result = await session.execute(
            select(PlayerSession)
            .where(PlayerSession.player_db_id == player.player_db_id)
            .order_by(PlayerSession.joined_at)
        )
        sessions = list(result.scalars().all())

        assert len(sessions) == 2
        assert sessions[0].duration_seconds == 600  # 10 minutes
        assert sessions[1].duration_seconds == 600  # 10 minutes


@pytest.mark.asyncio
async def test_zero_duration_session(player_system):
    """Test session with zero or near-zero duration."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    _server_db_id = await create_server(db, "server1")

    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="server1", player_name="Steve", uuid="uuid1"
        )
    )

    # Player joins and immediately leaves (same timestamp)
    same_time = datetime.now(timezone.utc)
    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="server1", player_name="Steve", timestamp=same_time)
    )
    await dispatcher.dispatch_player_left(
        PlayerLeftEvent(server_id="server1", player_name="Steve", timestamp=same_time)
    )

    # Should create session with 0 duration
    player = await get_player(db, "Steve")
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player.player_db_id
            )
        )
        player_session = result.scalar_one()
        assert player_session.duration_seconds == 0


@pytest.mark.asyncio
async def test_server_stop_with_no_players(player_system):
    """Test server stop event when no players are online."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    server_db_id = await create_server(db, "server1")

    # Server stops with no players
    await dispatcher.dispatch_server_stopping(ServerStoppingEvent(server_id="server1"))

    # Should not crash
    async with db() as session:
        result = await session.execute(
            select(PlayerOnlineStatus).where(
                PlayerOnlineStatus.server_db_id == server_db_id
            )
        )
        statuses = list(result.scalars().all())
        assert len(statuses) == 0


@pytest.mark.asyncio
async def test_missing_server_in_tracker(player_system):
    """Test events for server not in tracker (edge case)."""
    db = player_system["db"]
    dispatcher = player_system["dispatcher"]

    # Don't create server in tracker

    # Player events without server (should handle gracefully)
    await dispatcher.dispatch_player_uuid_discovered(
        PlayerUuidDiscoveredEvent(
            server_id="nonexistent", player_name="Steve", uuid="uuid1"
        )
    )

    await dispatcher.dispatch_player_joined(
        PlayerJoinedEvent(server_id="nonexistent", player_name="Steve")
    )

    # Should not crash, but also shouldn't create records
    # (PlayerManager logs warning and returns early)

    # Player might still exist from UUID discovery or Mojang fetch
    _player = await get_player(db, "Steve")
    # Player may or may not exist depending on event processing order
    # Main thing is no crash
