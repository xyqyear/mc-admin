"""
Integration tests for ServerTracker.

Tests server lifecycle tracking and event dispatching.
"""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base
from app.events.base import ServerCreatedEvent, ServerRemovedEvent
from app.models import Server, ServerStatus
from app.server_tracker import ServerTracker

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
def mock_mc_manager():
    """Mock Minecraft Docker manager."""
    manager = MagicMock()
    manager.get_all_server_names = AsyncMock(return_value=[])
    return manager


# ============================================================================
# Helper Functions
# ============================================================================


async def create_server_in_db(
    db, server_id: str, status: ServerStatus = ServerStatus.ACTIVE
):
    """Create server record in database."""
    async with db() as session:
        now = datetime.now(timezone.utc)
        server = Server(
            server_id=server_id,
            status=status,
            created_at=now,
            updated_at=now,
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)
        return server.id


async def get_server(db, server_id: str):
    """Get server from database."""
    async with db() as session:
        result = await session.execute(
            select(Server).where(Server.server_id == server_id)
        )
        return result.scalar_one_or_none()


async def get_all_servers(db):
    """Get all servers from database."""
    async with db() as session:
        result = await session.execute(select(Server))
        return list(result.scalars().all())


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_tracker_detects_new_server(
    test_database, clean_dispatcher, mock_mc_manager
):
    """Test tracker detects and creates new server."""
    db = test_database

    # Mock mc_manager to return one server
    mock_mc_manager.get_all_server_names = AsyncMock(return_value=["server1"])

    # Track events
    created_events = []

    async def track_created(event: ServerCreatedEvent):
        created_events.append(event.server_id)

    clean_dispatcher.on_server_created(track_created)

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
            sync_interval=0.1,  # Fast sync for testing
        )

        await tracker.start_tracking()

        # Wait for sync to happen
        await asyncio.sleep(0.2)

        # Check database
        server = await get_server(db, "server1")
        assert server is not None
        assert server.status == ServerStatus.ACTIVE

        # Check event
        assert "server1" in created_events

        await tracker.stop_tracking()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_tracker_detects_removed_server(
    test_database, clean_dispatcher, mock_mc_manager
):
    """Test tracker detects server removal."""
    db = test_database

    # Create server in database
    await create_server_in_db(db, "server1")

    # Mock mc_manager to return empty list (server removed from filesystem)
    mock_mc_manager.get_all_server_names = AsyncMock(return_value=[])

    # Track events
    removed_events = []

    async def track_removed(event: ServerRemovedEvent):
        removed_events.append(event.server_id)

    clean_dispatcher.on_server_removed(track_removed)

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
            sync_interval=0.1,
        )

        await tracker.start_tracking()

        # Wait for sync
        await asyncio.sleep(0.2)

        # Check database - server should be marked as removed
        server = await get_server(db, "server1")
        assert server is not None
        assert server.status == ServerStatus.REMOVED

        # Check event
        assert "server1" in removed_events

        await tracker.stop_tracking()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_tracker_detects_multiple_servers(
    test_database, clean_dispatcher, mock_mc_manager
):
    """Test tracker handles multiple servers."""
    db = test_database

    # Mock mc_manager to return multiple servers
    mock_mc_manager.get_all_server_names = AsyncMock(
        return_value=["server1", "server2", "server3"]
    )

    # Track events
    created_events = []

    async def track_created(event: ServerCreatedEvent):
        created_events.append(event.server_id)

    clean_dispatcher.on_server_created(track_created)

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
            sync_interval=0.1,
        )

        await tracker.start_tracking()
        await asyncio.sleep(0.2)

        # Check all servers created
        for server_id in ["server1", "server2", "server3"]:
            server = await get_server(db, server_id)
            assert server is not None
            assert server.status == ServerStatus.ACTIVE

        # Check events
        assert set(created_events) == {"server1", "server2", "server3"}

        await tracker.stop_tracking()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_tracker_sync_loop_continues_after_error(
    test_database, clean_dispatcher, mock_mc_manager
):
    """Test tracker continues syncing after errors."""
    db = test_database

    # Mock mc_manager to fail first time, then succeed
    call_count = {"count": 0}

    async def get_servers_with_error():
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise Exception("Simulated error")
        return ["server1"]

    mock_mc_manager.get_all_server_names = get_servers_with_error

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
            sync_interval=0.1,
        )

        await tracker.start_tracking()

        # Wait for multiple sync cycles
        await asyncio.sleep(0.3)

        # Should have retried and succeeded
        server = await get_server(db, "server1")
        assert server is not None

        await tracker.stop_tracking()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_tracker_get_server_db_id(
    test_database, clean_dispatcher, mock_mc_manager
):
    """Test tracker can get server database ID."""
    db = test_database

    # Create server
    server_db_id = await create_server_in_db(db, "server1")

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
        )

        # Get server DB ID
        result_id = await tracker.get_server_db_id("server1")
        assert result_id == server_db_id

        # Non-existent server
        result_id = await tracker.get_server_db_id("nonexistent")
        assert result_id is None

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_tracker_ignores_already_removed_servers(
    test_database, clean_dispatcher, mock_mc_manager
):
    """Test tracker doesn't re-emit events for already removed servers."""
    db = test_database

    # Create server already marked as removed
    await create_server_in_db(db, "server1", status=ServerStatus.REMOVED)

    # Mock mc_manager to return empty list
    mock_mc_manager.get_all_server_names = AsyncMock(return_value=[])

    # Track events
    removed_events = []

    async def track_removed(event: ServerRemovedEvent):
        removed_events.append(event.server_id)

    clean_dispatcher.on_server_removed(track_removed)

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
            sync_interval=0.1,
        )

        await tracker.start_tracking()
        await asyncio.sleep(0.2)

        # Should not emit event for already removed server
        assert "server1" not in removed_events

        await tracker.stop_tracking()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_tracker_handles_server_lifecycle(
    test_database, clean_dispatcher, mock_mc_manager
):
    """Test complete server lifecycle: create -> active -> remove."""
    db = test_database

    # Track events
    created_events = []
    removed_events = []

    async def track_created(event: ServerCreatedEvent):
        created_events.append(event.server_id)

    async def track_removed(event: ServerRemovedEvent):
        removed_events.append(event.server_id)

    clean_dispatcher.on_server_created(track_created)
    clean_dispatcher.on_server_removed(track_removed)

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
            sync_interval=0.1,
        )

        # Start with server present
        mock_mc_manager.get_all_server_names = AsyncMock(return_value=["server1"])

        await tracker.start_tracking()
        await asyncio.sleep(0.2)

        # Verify created
        assert "server1" in created_events
        server = await get_server(db, "server1")
        assert server.status == ServerStatus.ACTIVE

        # Remove server
        mock_mc_manager.get_all_server_names = AsyncMock(return_value=[])
        await asyncio.sleep(0.2)

        # Verify removed
        assert "server1" in removed_events
        server = await get_server(db, "server1")
        assert server.status == ServerStatus.REMOVED

        await tracker.stop_tracking()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_tracker_stops_cleanly(test_database, clean_dispatcher, mock_mc_manager):
    """Test tracker stops cleanly."""
    db = test_database

    patches = [
        patch("app.db.database.get_async_session", db),
        patch("app.server_tracker.tracker.get_async_session", db),
    ]

    for p in patches:
        p.start()

    try:
        tracker = ServerTracker(
            mc_manager=mock_mc_manager,
            event_dispatcher=clean_dispatcher,
            sync_interval=0.1,
        )

        await tracker.start_tracking()
        await asyncio.sleep(0.05)

        # Stop should complete without errors
        await tracker.stop_tracking()

        # Verify task is cancelled
        assert tracker._sync_task is not None
        assert tracker._sync_task.cancelled() or tracker._sync_task.done()

    finally:
        for p in patches:
            p.stop()
