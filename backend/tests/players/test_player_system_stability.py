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
from app.models import (
    Player,
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
)
from tests.players.helpers import make_online_uuid

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
        return make_online_uuid(player_name)

    return AsyncMock(side_effect=fetch_uuid)


@pytest.fixture
async def player_system(test_database, mock_skin_fetcher, mock_mojang_api):
    """Initialize player system."""
    patches = [
        patch("app.players.tracking.get_async_session", test_database),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
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


async def count_open_sessions(db, player_db_id: int):
    """Count open (not yet ended) player sessions."""
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player_db_id,
                PlayerSession.left_at == None,  # noqa: E711
            )
        )
        return len(list(result.scalars().all()))


# ============================================================================
# Concurrency Tests
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_events_same_player(player_system):
    """Test concurrent calls for same player are handled correctly."""
    db = player_system["db"]

    _server_db_id = await create_server(db, "server1")

    # Upsert player UUID
    async with db() as session:
        await upsert_player(session, make_online_uuid("Steve"), "Steve")

    # Concurrent joins (simulating race condition — each gets its own DB session)
    join_time = datetime.now(timezone.utc)

    await asyncio.gather(
        process_player_join("server1", "Steve", timestamp=join_time),
        process_player_join(
            "server1", "Steve", timestamp=join_time + timedelta(seconds=1)
        ),
    )

    # System should handle this gracefully — no errors
    player = await get_player(db, "Steve")
    assert player is not None

    # Sequential leave after all joins complete — must close ALL open sessions
    await process_player_left(
        "server1", "Steve", timestamp=join_time + timedelta(seconds=2)
    )

    # No orphan open sessions should remain
    open_count = await count_open_sessions(db, player.player_db_id)
    assert open_count == 0


@pytest.mark.asyncio
async def test_rapid_server_stop_events(player_system):
    """Test rapid server stop calls are handled correctly."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    # Create players
    for i in range(5):
        async with db() as session:
            await upsert_player(session, make_online_uuid(f"Player{i}"), f"Player{i}")
        await process_player_join("server1", f"Player{i}")

    # Multiple rapid close_server_sessions calls
    await asyncio.gather(*[close_server_sessions("server1") for _ in range(10)])

    # All players should be offline (all sessions should be ended)
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
async def test_concurrent_multi_server_events(player_system):
    """Test concurrent calls across multiple servers."""
    db = player_system["db"]

    # Create 3 servers
    servers = []
    for i in range(3):
        server_id = await create_server(db, f"server{i}")
        servers.append((f"server{i}", server_id))

    # Upsert player UUID
    async with db() as session:
        await upsert_player(session, make_online_uuid("Steve"), "Steve")

    # Player joins all 3 servers concurrently
    await asyncio.gather(
        *[process_player_join(server_id, "Steve") for server_id, _ in servers]
    )

    # Verify online on all servers (has open sessions on all servers)
    player = await get_player(db, "Steve")
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player.player_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        open_sessions = list(result.scalars().all())
        assert len(open_sessions) == 3


# ============================================================================
# Edge Case Stress Tests
# ============================================================================


@pytest.mark.asyncio
async def test_massive_player_count(player_system):
    """Test system handles large number of concurrent players."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    # 100 players
    player_count = 100

    # Upsert all player UUIDs
    for i in range(player_count):
        async with db() as session:
            await upsert_player(session, make_online_uuid(f"Player{i}"), f"Player{i}")

    # All join
    join_tasks = [
        process_player_join("server1", f"Player{i}") for i in range(player_count)
    ]
    await asyncio.gather(*join_tasks)

    # Verify all online (have open sessions)
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.server_db_id == server_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        open_sessions = list(result.scalars().all())
        assert len(open_sessions) == player_count

    # Half leave
    leave_tasks = [
        process_player_left("server1", f"Player{i}") for i in range(player_count // 2)
    ]
    await asyncio.gather(*leave_tasks)

    # Verify correct count (half still have open sessions)
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.server_db_id == server_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        open_sessions = list(result.scalars().all())
        assert len(open_sessions) == player_count // 2


@pytest.mark.asyncio
async def test_session_without_leave(player_system):
    """Test open sessions without leave events."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    # Multiple players join but never leave
    for i in range(10):
        async with db() as session:
            await upsert_player(session, make_online_uuid(f"Player{i}"), f"Player{i}")
        await process_player_join("server1", f"Player{i}")

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
    await close_server_sessions("server1")

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

    _server_db_id = await create_server(db, "server1")

    async with db() as session:
        await upsert_player(session, make_online_uuid("Steve"), "Steve")

    # Player joins 1 day ago
    join_time = datetime.now(timezone.utc) - timedelta(days=1)
    await process_player_join("server1", "Steve", timestamp=join_time)

    # Player leaves after 24 hours
    leave_time = join_time + timedelta(days=1)
    await process_player_left("server1", "Steve", timestamp=leave_time)

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
    """Test calls are processed in order for same player."""
    db = player_system["db"]

    _server_db_id = await create_server(db, "server1")

    # Precise timing for events
    base_time = datetime.now(timezone.utc)

    # Upsert UUID
    async with db() as session:
        await upsert_player(session, make_online_uuid("Steve"), "Steve")

    # Session 1: 0-10 minutes
    await process_player_join("server1", "Steve", timestamp=base_time)
    await process_player_left(
        "server1", "Steve", timestamp=base_time + timedelta(minutes=10)
    )

    # Session 2: 20-30 minutes
    await process_player_join(
        "server1", "Steve", timestamp=base_time + timedelta(minutes=20)
    )
    await process_player_left(
        "server1", "Steve", timestamp=base_time + timedelta(minutes=30)
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

    _server_db_id = await create_server(db, "server1")

    async with db() as session:
        await upsert_player(session, make_online_uuid("Steve"), "Steve")

    # Player joins and immediately leaves (same timestamp)
    same_time = datetime.now(timezone.utc)
    await process_player_join("server1", "Steve", timestamp=same_time)
    await process_player_left("server1", "Steve", timestamp=same_time)

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
    """Test server stop when no players are online."""
    db = player_system["db"]

    server_db_id = await create_server(db, "server1")

    # Server stops with no players
    await close_server_sessions("server1")

    # Should not crash (no sessions should exist)
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(PlayerSession.server_db_id == server_db_id)
        )
        sessions = list(result.scalars().all())
        assert len(sessions) == 0


@pytest.mark.asyncio
async def test_missing_server_in_tracker(player_system):
    """Test calls for server not in database (edge case)."""
    db = player_system["db"]

    # Don't create server in database

    # Upsert player UUID
    async with db() as session:
        await upsert_player(session, make_online_uuid("Steve"), "Steve")

    # Player join on nonexistent server (should handle gracefully)
    await process_player_join("nonexistent", "Steve")

    # Should not crash, but also shouldn't create session records
    # (tracking functions log warning and return early)

    # Player may still exist from the upsert
    _player = await get_player(db, "Steve")
    # Main thing is no crash
