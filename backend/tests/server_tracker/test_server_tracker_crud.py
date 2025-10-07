"""
Unit tests for ServerTracker CRUD operations.

Tests database operations for server tracking.
"""

import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base
from app.models import Server, ServerStatus
from app.server_tracker.crud import (
    create_server,
    get_active_servers,
    get_active_servers_map,
    get_server_by_id,
    get_server_db_id,
    mark_server_removed,
)

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


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_server(test_database):
    """Test creating a server record."""
    db = test_database

    async with db() as session:
        now = datetime.now(timezone.utc)
        server = await create_server(session, "test_server", now)

        assert server.server_id == "test_server"
        assert server.status == ServerStatus.ACTIVE
        assert server.created_at == now
        assert server.updated_at == now
        assert server.id > 0


@pytest.mark.asyncio
async def test_get_active_servers(test_database):
    """Test getting active servers."""
    db = test_database

    # Create active servers
    async with db() as session:
        now = datetime.now(timezone.utc)
        await create_server(session, "server1", now)
        await create_server(session, "server2", now)

    # Create removed server
    async with db() as session:
        server = Server(
            server_id="removed_server",
            status=ServerStatus.REMOVED,
            created_at=now,
            updated_at=now,
        )
        session.add(server)
        await session.commit()

    # Get active servers
    async with db() as session:
        active_servers = await get_active_servers(session)

    assert len(active_servers) == 2
    server_ids = {s.server_id for s in active_servers}
    assert server_ids == {"server1", "server2"}


@pytest.mark.asyncio
async def test_get_active_servers_map(test_database):
    """Test getting active servers as a map."""
    db = test_database

    # Create servers
    async with db() as session:
        now = datetime.now(timezone.utc)
        server1 = await create_server(session, "server1", now)

    async with db() as session:
        server2 = await create_server(session, "server2", now)

    # Get map
    async with db() as session:
        server_map = await get_active_servers_map(session)

    assert len(server_map) == 2
    assert server_map["server1"] == server1.id
    assert server_map["server2"] == server2.id


@pytest.mark.asyncio
async def test_get_server_by_id(test_database):
    """Test getting server by identifier."""
    db = test_database

    # Create server
    async with db() as session:
        now = datetime.now(timezone.utc)
        await create_server(session, "test_server", now)

    # Get server
    async with db() as session:
        server = await get_server_by_id(session, "test_server")

    assert server is not None
    assert server.server_id == "test_server"

    # Get non-existent server
    async with db() as session:
        server = await get_server_by_id(session, "nonexistent")

    assert server is None


@pytest.mark.asyncio
async def test_get_server_db_id(test_database):
    """Test getting server database ID."""
    db = test_database

    # Create server
    async with db() as session:
        now = datetime.now(timezone.utc)
        created_server = await create_server(session, "test_server", now)

    # Get DB ID
    async with db() as session:
        db_id = await get_server_db_id(session, "test_server")

    assert db_id == created_server.id

    # Get non-existent server
    async with db() as session:
        db_id = await get_server_db_id(session, "nonexistent")

    assert db_id is None


@pytest.mark.asyncio
async def test_mark_server_removed(test_database):
    """Test marking server as removed."""
    db = test_database

    # Create server
    async with db() as session:
        now = datetime.now(timezone.utc)
        await create_server(session, "test_server", now)

    # Mark as removed
    async with db() as session:
        updated_at = datetime.now(timezone.utc)
        await mark_server_removed(session, "test_server", updated_at)

    # Verify status
    async with db() as session:
        server = await get_server_by_id(session, "test_server")

    assert server is not None
    assert server.status == ServerStatus.REMOVED
    assert server.updated_at == updated_at


@pytest.mark.asyncio
async def test_mark_server_removed_only_active(test_database):
    """Test mark_server_removed only affects active servers."""
    db = test_database

    now = datetime.now(timezone.utc)

    # Create already removed server
    async with db() as session:
        server = Server(
            server_id="already_removed",
            status=ServerStatus.REMOVED,
            created_at=now,
            updated_at=now,
        )
        session.add(server)
        await session.commit()

    # Try to mark as removed again
    async with db() as session:
        new_time = datetime.now(timezone.utc)
        await mark_server_removed(session, "already_removed", new_time)

    # Verify timestamp not updated (WHERE clause prevents update)
    async with db() as session:
        server = await get_server_by_id(session, "already_removed")

    assert server is not None

    assert server.updated_at == now  # Original time, not new_time


@pytest.mark.asyncio
async def test_multiple_server_operations(test_database):
    """Test multiple operations on servers."""
    db = test_database

    now = datetime.now(timezone.utc)

    # Create multiple servers
    async with db() as session:
        await create_server(session, "server1", now)

    async with db() as session:
        await create_server(session, "server2", now)

    async with db() as session:
        await create_server(session, "server3", now)

    # Get all active
    async with db() as session:
        active_servers = await get_active_servers(session)
    assert len(active_servers) == 3

    # Remove one
    async with db() as session:
        await mark_server_removed(session, "server2", datetime.now(timezone.utc))

    # Verify only 2 active
    async with db() as session:
        active_servers = await get_active_servers(session)
    assert len(active_servers) == 2
    server_ids = {s.server_id for s in active_servers}
    assert server_ids == {"server1", "server3"}


@pytest.mark.asyncio
async def test_get_active_servers_empty(test_database):
    """Test getting active servers when none exist."""
    db = test_database

    async with db() as session:
        active_servers = await get_active_servers(session)

    assert active_servers == []


@pytest.mark.asyncio
async def test_get_active_servers_map_empty(test_database):
    """Test getting active servers map when none exist."""
    db = test_database

    async with db() as session:
        server_map = await get_active_servers_map(session)

    assert server_map == {}


# ============================================================================
# Tests for Multiple Servers with Same server_id (Recreate Scenario)
# ============================================================================


@pytest.mark.asyncio
async def test_get_server_by_id_prefers_active_over_removed(test_database):
    """Test that ACTIVE server is preferred over REMOVED when both exist."""
    db = test_database

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Create first server (will be marked as REMOVED)
    async with db() as session:
        server1 = Server(
            server_id="test_server",
            status=ServerStatus.REMOVED,
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=1),
        )
        session.add(server1)
        await session.commit()
        await session.refresh(server1)
        _first_id = server1.id

    # Create second server (ACTIVE, newer)
    async with db() as session:
        server2 = Server(
            server_id="test_server",
            status=ServerStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(server2)
        await session.commit()
        await session.refresh(server2)
        second_id = server2.id

    # Should return the ACTIVE server (server2)
    async with db() as session:
        result = await get_server_by_id(session, "test_server")

    assert result is not None
    assert result.id == second_id
    assert result.status == ServerStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_server_by_id_multiple_active_returns_newest(test_database):
    """Test that when multiple ACTIVE servers exist, the newest one is returned."""
    db = test_database

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Create older ACTIVE server
    async with db() as session:
        server1 = Server(
            server_id="test_server",
            status=ServerStatus.ACTIVE,
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        )
        session.add(server1)
        await session.commit()
        await session.refresh(server1)
        _first_id = server1.id

    # Create newer ACTIVE server
    async with db() as session:
        server2 = Server(
            server_id="test_server",
            status=ServerStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(server2)
        await session.commit()
        await session.refresh(server2)
        second_id = server2.id

    # Should return the newer ACTIVE server (server2)
    async with db() as session:
        result = await get_server_by_id(session, "test_server")

    assert result is not None
    assert result.id == second_id
    assert result.created_at == now


@pytest.mark.asyncio
async def test_get_server_by_id_only_removed_returns_newest(test_database):
    """Test that when only REMOVED servers exist, the newest one is returned."""
    db = test_database

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Create older REMOVED server
    async with db() as session:
        server1 = Server(
            server_id="test_server",
            status=ServerStatus.REMOVED,
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=1),
        )
        session.add(server1)
        await session.commit()
        await session.refresh(server1)
        _first_id = server1.id

    # Create newer REMOVED server
    async with db() as session:
        server2 = Server(
            server_id="test_server",
            status=ServerStatus.REMOVED,
            created_at=now,
            updated_at=now,
        )
        session.add(server2)
        await session.commit()
        await session.refresh(server2)
        second_id = server2.id

    # Should return the newer REMOVED server (server2)
    async with db() as session:
        result = await get_server_by_id(session, "test_server")

    assert result is not None
    assert result.id == second_id
    assert result.created_at == now


@pytest.mark.asyncio
async def test_get_server_by_id_race_condition_scenario(test_database):
    """Test race condition scenario: server marked REMOVED but player events still processing."""
    db = test_database

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Create and then mark server as REMOVED (simulating server shutdown)
    async with db() as session:
        server = Server(
            server_id="test_server",
            status=ServerStatus.REMOVED,  # Already marked as removed
            created_at=now - timedelta(minutes=5),
            updated_at=now - timedelta(seconds=1),
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)
        server_id_value = server.id

    # Player events (like PlayerLeftEvent, ServerStoppingEvent) should still find the server
    async with db() as session:
        result = await get_server_by_id(session, "test_server")

    assert result is not None
    assert result.id == server_id_value
    assert result.status == ServerStatus.REMOVED


@pytest.mark.asyncio
async def test_get_server_db_id_with_multiple_servers(test_database):
    """Test get_server_db_id returns correct ID when multiple servers exist."""
    db = test_database

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Create old REMOVED server
    async with db() as session:
        server1 = Server(
            server_id="test_server",
            status=ServerStatus.REMOVED,
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(minutes=30),
        )
        session.add(server1)
        await session.commit()
        await session.refresh(server1)
        _first_id = server1.id

    # Create new ACTIVE server
    async with db() as session:
        server2 = Server(
            server_id="test_server",
            status=ServerStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(server2)
        await session.commit()
        await session.refresh(server2)
        second_id = server2.id

    # Should return the database ID of the ACTIVE server (server2)
    async with db() as session:
        db_id = await get_server_db_id(session, "test_server")

    assert db_id == second_id


@pytest.mark.asyncio
async def test_server_recreate_lifecycle(test_database):
    """Test complete server lifecycle: create -> remove -> recreate."""
    db = test_database

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Step 1: Create first server
    async with db() as session:
        server1 = await create_server(session, "test_server", now - timedelta(hours=2))
        first_db_id = server1.id
        assert server1.status == ServerStatus.ACTIVE

    # Step 2: Mark first server as removed
    async with db() as session:
        await mark_server_removed(session, "test_server", now - timedelta(hours=1))

    # Verify first server is now REMOVED
    async with db() as session:
        result = await get_server_by_id(session, "test_server")
    assert result is not None
    assert result.id == first_db_id
    assert result.status == ServerStatus.REMOVED

    # Step 3: Create second server with same server_id (recreate scenario)
    async with db() as session:
        server2 = await create_server(session, "test_server", now)
        second_db_id = server2.id
        assert second_db_id != first_db_id  # Different database ID
        assert server2.status == ServerStatus.ACTIVE

    # Step 4: Now get_server_by_id should return the new ACTIVE server
    async with db() as session:
        result = await get_server_by_id(session, "test_server")
    assert result is not None
    assert result.id == second_db_id
    assert result.status == ServerStatus.ACTIVE

    # Step 5: Mark second server as removed
    async with db() as session:
        await mark_server_removed(session, "test_server", now)

    # Should now return the most recently removed server (server2)
    async with db() as session:
        result = await get_server_by_id(session, "test_server")
    assert result is not None
    assert result.id == second_db_id
    assert result.status == ServerStatus.REMOVED
