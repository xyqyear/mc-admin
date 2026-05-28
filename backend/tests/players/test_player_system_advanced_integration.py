"""
Advanced integration tests for player management system.

Tests system crash recovery and RCON validation scenarios.
"""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base
from app.minecraft.instance import MCServerStatus
from app.models import (
    Player,
    PlayerSession,
    Server,
    ServerStatus,
    SystemHeartbeat,
)
from app.players.heartbeat import HeartbeatManager
from app.players.player_syncer import PlayerSyncer
from app.players.skin_fetcher import SkinFetcher
from tests.players.helpers import make_online_uuid

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
        return (b"skin_" + uuid.encode(), b"avatar_" + uuid.encode())

    return AsyncMock(side_effect=fetch_skin)


@pytest.fixture
def mock_mojang_api():
    """Mock Mojang API with 200ms network delay."""

    async def fetch_uuid(player_name: str):
        await asyncio.sleep(0.2)
        return make_online_uuid(player_name)

    return AsyncMock(side_effect=fetch_uuid)


@pytest.fixture
def mock_config():
    """Mock dynamic configuration."""
    config = MagicMock()

    # Heartbeat config
    heartbeat_config = MagicMock()
    heartbeat_config.heartbeat_interval_seconds = 0.1  # Fast for testing
    heartbeat_config.crash_threshold_minutes = 1
    config.players.heartbeat = heartbeat_config

    # RCON validation config
    rcon_config = MagicMock()
    rcon_config.validation_interval_seconds = 0.1  # Fast for testing
    config.players.rcon_validation = rcon_config

    return config


# ============================================================================
# Helper Functions
# ============================================================================


async def create_server(db, server_id: str, is_active: bool = True) -> int:
    """Create server in database."""
    async with db() as session:
        now = datetime.now(timezone.utc)
        server = Server(
            server_id=server_id,
            status=ServerStatus.ACTIVE if is_active else ServerStatus.REMOVED,
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


async def get_online_players(db, server_db_id: int):
    """Get all online players on server (players with open sessions)."""
    async with db() as session:
        result = await session.execute(
            select(PlayerSession).where(
                PlayerSession.server_db_id == server_db_id,
                PlayerSession.left_at.is_(None),
            )
        )
        return list(result.scalars().all())


async def get_heartbeat(db):
    """Get the single heartbeat record."""
    async with db() as session:
        result = await session.execute(
            select(SystemHeartbeat).where(SystemHeartbeat.id == 1)
        )
        return result.scalar_one_or_none()


async def create_heartbeat(db, timestamp: datetime):
    """Create or update the single heartbeat record."""
    from sqlalchemy.dialects.sqlite import insert

    async with db() as session:
        stmt = insert(SystemHeartbeat).values(
            id=1,
            timestamp=timestamp,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"timestamp": timestamp},
        )
        await session.execute(stmt)
        await session.commit()


async def set_player_online(db, player_db_id: int, server_db_id: int):
    """Manually set player online (for testing) by creating open session."""
    async with db() as session:
        player_session = PlayerSession(
            player_db_id=player_db_id,
            server_db_id=server_db_id,
            joined_at=datetime.now(timezone.utc),
            left_at=None,
            duration_seconds=None,
        )
        session.add(player_session)
        await session.commit()


# ============================================================================
# Heartbeat and Crash Recovery Tests
# ============================================================================


@pytest.mark.asyncio
async def test_heartbeat_normal_startup(test_database, mock_config):
    """Test normal startup with recent heartbeat (no crash)."""
    db = test_database

    # Create recent heartbeat (30 seconds ago)
    recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    await create_heartbeat(db, recent_time)

    patches = [
        patch("app.players.heartbeat.get_async_session", db),
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.heartbeat.config", mock_config),
    ]

    for p in patches:
        p.start()

    try:
        heartbeat_manager = HeartbeatManager()

        # Start heartbeat (should detect normal restart)
        await heartbeat_manager.start()
        await asyncio.sleep(0.2)  # Let it run

        # Should have new heartbeat
        heartbeat = await get_heartbeat(db)
        assert heartbeat is not None
        assert heartbeat.timestamp > recent_time

        await heartbeat_manager.stop()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_heartbeat_crash_detection(
    test_database, mock_config, mock_skin_fetcher, mock_mojang_api
):
    """Test crash detection and recovery when heartbeat is stale."""
    db = test_database

    # Create server and players
    server_db_id = await create_server(db, "server1")

    # Create stale heartbeat (2 hours ago - beyond threshold)
    stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
    await create_heartbeat(db, stale_time)

    # Manually set players online
    async with db() as session:
        for name in ["Steve", "Alex"]:
            player = Player(
                uuid=make_online_uuid(name),
                current_name=name,
                created_at=datetime.now(timezone.utc),
            )
            session.add(player)
        await session.commit()

    steve = await get_player(db, "Steve")
    alex = await get_player(db, "Alex")
    await set_player_online(db, steve.player_db_id, server_db_id)
    await set_player_online(db, alex.player_db_id, server_db_id)

    # Verify they are online before crash recovery
    online = await get_online_players(db, server_db_id)
    assert len(online) == 2

    # Mock player_syncer.validate_all_servers to avoid needing docker_mc_manager
    from app.players.player_syncer import player_syncer as ps_singleton

    mock_validate = AsyncMock()

    patches = [
        patch("app.players.heartbeat.get_async_session", db),
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.heartbeat.config", mock_config),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
        patch.object(ps_singleton, "validate_all_servers", mock_validate),
    ]

    for p in patches:
        p.start()

    try:
        heartbeat_manager = HeartbeatManager()

        # Start heartbeat (should detect crash and call process_player_left)
        await heartbeat_manager.start()

        # Give time for crash recovery to complete
        await asyncio.sleep(0.3)

        # Verify all players marked offline (no open sessions)
        online = await get_online_players(db, server_db_id)
        assert len(online) == 0

        # Verify all sessions have been ended with left_at timestamp at crash time
        async with db() as session:
            result = await session.execute(
                select(PlayerSession).where(PlayerSession.server_db_id == server_db_id)
            )
            sessions = list(result.scalars().all())
            for player_session in sessions:
                assert player_session.left_at is not None
                assert player_session.duration_seconds is not None
                # Should be ended at stale heartbeat time
                assert abs((player_session.left_at - stale_time).total_seconds()) < 1

        # validate_all_servers should have been called during crash recovery
        mock_validate.assert_called_once()

        await heartbeat_manager.stop()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_heartbeat_continuous_updates(test_database, mock_config):
    """Test heartbeat continuously updates the single record during normal operation."""
    db = test_database

    patches = [
        patch("app.players.heartbeat.get_async_session", db),
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.heartbeat.config", mock_config),
    ]

    for p in patches:
        p.start()

    try:
        heartbeat_manager = HeartbeatManager()

        await heartbeat_manager.start()

        # Get initial timestamp
        await asyncio.sleep(0.1)
        first_heartbeat = await get_heartbeat(db)
        assert first_heartbeat is not None
        first_timestamp = first_heartbeat.timestamp

        # Wait for multiple heartbeat intervals
        await asyncio.sleep(0.5)  # Should have ~5 updates

        # Check that only one record exists and it was updated
        async with db() as session:
            result = await session.execute(select(SystemHeartbeat))
            heartbeats = list(result.scalars().all())
            assert len(heartbeats) == 1  # Should have exactly one heartbeat record
            assert heartbeats[0].id == 1  # Should be id=1
            assert heartbeats[0].timestamp > first_timestamp  # Should be updated

        await heartbeat_manager.stop()

    finally:
        for p in patches:
            p.stop()


# ============================================================================
# RCON Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_player_syncer_corrects_false_positives(
    test_database, mock_config, mock_skin_fetcher, mock_mojang_api
):
    """Test RCON validator corrects players marked online but not in RCON."""
    db = test_database

    server_db_id = await create_server(db, "server1", is_active=True)

    # Create players and mark online
    async with db() as session:
        for name in ["Steve", "Alex", "Bob"]:
            player = Player(
                uuid=make_online_uuid(name),
                current_name=name,
                created_at=datetime.now(timezone.utc),
            )
            session.add(player)
        await session.commit()

    steve = await get_player(db, "Steve")
    alex = await get_player(db, "Alex")
    bob = await get_player(db, "Bob")

    await set_player_online(db, steve.player_db_id, server_db_id)
    await set_player_online(db, alex.player_db_id, server_db_id)
    await set_player_online(db, bob.player_db_id, server_db_id)

    # Mock MCInstance to return only Steve and Alex (Bob is false positive)
    mock_instance = MagicMock()
    mock_instance.get_status = AsyncMock(return_value=MCServerStatus.HEALTHY)
    mock_instance.list_players = AsyncMock(return_value=["Steve", "Alex"])

    # Mock DockerMCManager
    mock_mc_manager = MagicMock()
    mock_mc_manager.get_instance = MagicMock(return_value=mock_instance)

    patches = [
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.player_syncer.get_async_session", db),
        patch("app.players.player_syncer.docker_mc_manager", mock_mc_manager),
        patch("app.players.player_syncer.config", mock_config),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ]

    for p in patches:
        p.start()

    try:
        player_syncer = PlayerSyncer()

        await player_syncer.start()

        # Wait for validation
        await asyncio.sleep(0.3)

        # Bob should have been marked offline
        # Verify database state
        online = await get_online_players(db, server_db_id)
        online_names = set()
        for status in online:
            async with db() as session:
                result = await session.execute(
                    select(Player).where(Player.player_db_id == status.player_db_id)
                )
                player = result.scalar_one()
                online_names.add(player.current_name)

        assert online_names == {"Steve", "Alex"}

        await player_syncer.stop()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_player_syncer_corrects_false_negatives(
    test_database, mock_config, mock_skin_fetcher, mock_mojang_api
):
    """Test RCON validator corrects players in RCON but not marked online."""
    db = test_database

    server_db_id = await create_server(db, "server1", is_active=True)

    # Create players (not marked online)
    async with db() as session:
        for name in ["Steve", "Alex"]:
            player = Player(
                uuid=make_online_uuid(name),
                current_name=name,
                created_at=datetime.now(timezone.utc),
            )
            session.add(player)
        await session.commit()

    # Verify players were created
    async with db() as session:
        result = await session.execute(select(Player))
        players = result.scalars().all()
        assert len(players) == 2, f"Expected 2 players, got {len(players)}"

    # Mock MCInstance to return Steve and Alex (but they're not in DB as online)
    mock_instance = MagicMock()
    mock_instance.get_status = AsyncMock(return_value=MCServerStatus.HEALTHY)
    mock_instance.list_players = AsyncMock(return_value=["Steve", "Alex"])

    mock_mc_manager = MagicMock()
    mock_mc_manager.get_instance = MagicMock(return_value=mock_instance)

    patches = [
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.player_syncer.get_async_session", db),
        patch("app.players.player_syncer.docker_mc_manager", mock_mc_manager),
        patch("app.players.player_syncer.config", mock_config),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ]

    for p in patches:
        p.start()

    try:
        player_syncer = PlayerSyncer()

        await player_syncer.start()

        # Wait for validation (need enough time for both players to be processed)
        await asyncio.sleep(0.8)

        # Both should have been marked online
        online = await get_online_players(db, server_db_id)
        assert len(online) == 2

        await player_syncer.stop()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_player_syncer_skips_unhealthy_servers(test_database, mock_config):
    """Test RCON validator skips servers that are not healthy."""
    db = test_database
    await create_server(db, "server1", is_active=True)

    # Mock MCInstance with unhealthy status
    mock_instance = MagicMock()
    mock_instance.get_status = AsyncMock(return_value=MCServerStatus.RUNNING)
    mock_instance.list_players = AsyncMock(
        side_effect=Exception("Should not be called")
    )

    mock_mc_manager = MagicMock()
    mock_mc_manager.get_instance = MagicMock(return_value=mock_instance)

    patches = [
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.player_syncer.get_async_session", db),
        patch("app.players.player_syncer.docker_mc_manager", mock_mc_manager),
        patch("app.players.player_syncer.config", mock_config),
    ]

    for p in patches:
        p.start()

    try:
        player_syncer = PlayerSyncer()

        await player_syncer.start()
        await asyncio.sleep(0.3)

        # Should not crash, list_players should not be called
        mock_instance.list_players.assert_not_called()

        await player_syncer.stop()

    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_player_syncer_handles_rcon_failure(test_database, mock_config):
    """Test RCON validator handles RCON command failures gracefully."""
    db = test_database
    await create_server(db, "server1", is_active=True)

    # Mock MCInstance that fails RCON
    mock_instance = MagicMock()
    mock_instance.get_status = AsyncMock(return_value=MCServerStatus.HEALTHY)
    mock_instance.list_players = AsyncMock(side_effect=Exception("RCON failed"))

    mock_mc_manager = MagicMock()
    mock_mc_manager.get_instance = MagicMock(return_value=mock_instance)

    patches = [
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.player_syncer.get_async_session", db),
        patch("app.players.player_syncer.docker_mc_manager", mock_mc_manager),
        patch("app.players.player_syncer.config", mock_config),
    ]

    for p in patches:
        p.start()

    try:
        player_syncer = PlayerSyncer()

        await player_syncer.start()
        await asyncio.sleep(0.3)

        # Should not crash, just log warning
        await player_syncer.stop()

    finally:
        for p in patches:
            p.stop()


# ============================================================================
# Combined Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_crash_recovery_triggers_rcon_validation(
    test_database, mock_config, mock_skin_fetcher, mock_mojang_api
):
    """Test crash recovery triggers RCON validation to fix states."""
    db = test_database

    server_db_id = await create_server(db, "server1", is_active=True)

    # Create stale heartbeat
    stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
    await create_heartbeat(db, stale_time)

    # Create players marked online (but may not actually be online)
    async with db() as session:
        for name in ["Steve", "Alex", "Bob"]:
            player = Player(
                uuid=make_online_uuid(name),
                current_name=name,
                created_at=datetime.now(timezone.utc),
            )
            session.add(player)
        await session.commit()

    steve = await get_player(db, "Steve")
    alex = await get_player(db, "Alex")
    bob = await get_player(db, "Bob")

    await set_player_online(db, steve.player_db_id, server_db_id)
    await set_player_online(db, alex.player_db_id, server_db_id)
    await set_player_online(db, bob.player_db_id, server_db_id)

    # Mock RCON to return only Steve (Alex and Bob are false positives)
    mock_instance = MagicMock()
    mock_instance.get_status = AsyncMock(return_value=MCServerStatus.HEALTHY)
    mock_instance.list_players = AsyncMock(return_value=["Steve"])

    mock_mc_manager = MagicMock()
    mock_mc_manager.get_instance = MagicMock(return_value=mock_instance)

    patches = [
        patch("app.players.heartbeat.get_async_session", db),
        patch("app.players.heartbeat.config", mock_config),
        patch("app.players.tracking.get_async_session", db),
        patch("app.players.player_syncer.get_async_session", db),
        patch("app.players.player_syncer.docker_mc_manager", mock_mc_manager),
        patch("app.players.player_syncer.config", mock_config),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ]

    for p in patches:
        p.start()

    try:
        heartbeat_manager = HeartbeatManager()

        # Start heartbeat (detects crash, calls process_player_left for all,
        # then calls player_syncer.validate_all_servers)
        await heartbeat_manager.start()

        # Wait for crash recovery to complete
        await asyncio.sleep(0.5)

        # All players should be marked offline by crash recovery first
        # Then RCON validation (called during crash recovery) should re-add Steve
        online = await get_online_players(db, server_db_id)
        assert len(online) == 1

        async with db() as session:
            result = await session.execute(
                select(Player).where(Player.player_db_id == online[0].player_db_id)
            )
            online_player = result.scalar_one()
            assert online_player.current_name == "Steve"

        await heartbeat_manager.stop()

    finally:
        for p in patches:
            p.stop()
