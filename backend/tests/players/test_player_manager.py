"""Tests for PlayerManager."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.events.base import (
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerSkinUpdateRequestedEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
)
from app.events.dispatcher import EventDispatcher
from app.models import Base, Player, PlayerOnlineStatus, Server, ServerStatus
from app.players.player_manager import PlayerManager


@pytest.fixture
async def test_db_engine():
    """Create a temporary in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine):
    """Create a test database session."""
    async_session = async_sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session


@pytest.fixture
async def test_server(test_db_session):
    """Create a test server in the database."""
    server = Server(
        id=1,
        server_id="test_server",
        status=ServerStatus.ACTIVE,
    )
    test_db_session.add(server)
    await test_db_session.commit()
    return server


@pytest.fixture
async def test_player(test_db_session):
    """Create a test player in the database."""
    player = Player(
        player_db_id=1,
        uuid="test_uuid_123",
        current_name="TestPlayer",
        created_at=datetime.now(timezone.utc),
    )
    test_db_session.add(player)
    await test_db_session.commit()
    return player


class TestPlayerManager:
    """Test PlayerManager functionality."""

    @pytest.mark.asyncio
    async def test_handle_uuid_discovered(self, test_db_session):
        """Test handling player UUID discovery event."""
        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and player manager
            dispatcher = EventDispatcher()
            PlayerManager(dispatcher)

            # Create UUID discovered event
            event = PlayerUuidDiscoveredEvent(
                server_id="test_server",
                player_name="NewPlayer",
                uuid="discovered_uuid_999",
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event
            await dispatcher.dispatch_player_uuid_discovered(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify player was created/updated
            result = await test_db_session.execute(
                select(Player).where(Player.uuid == "discovered_uuid_999")
            )
            player = result.scalar_one_or_none()

            assert player is not None
            assert player.current_name == "NewPlayer"
            assert player.uuid == "discovered_uuid_999"

    @pytest.mark.asyncio
    async def test_handle_player_joined_existing_player(
        self, test_db_session, test_server, test_player
    ):
        """Test handling player join event for existing player."""
        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and player manager
            dispatcher = EventDispatcher()
            PlayerManager(dispatcher)

            # Create player joined event
            join_time = datetime.now(timezone.utc)
            event = PlayerJoinedEvent(
                server_id="test_server",
                player_name="TestPlayer",
                timestamp=join_time,
            )

            # Dispatch event
            await dispatcher.dispatch_player_joined(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify online status was created
            result = await test_db_session.execute(
                select(PlayerOnlineStatus).where(
                    PlayerOnlineStatus.player_db_id == test_player.player_db_id,
                    PlayerOnlineStatus.server_db_id == test_server.id,
                )
            )
            status = result.scalar_one_or_none()

            assert status is not None
            assert status.is_online is True
            assert status.last_join == join_time

            # Verify last_seen was updated
            await test_db_session.refresh(test_player)
            assert test_player.last_seen == join_time

    @pytest.mark.asyncio
    async def test_handle_player_joined_new_player(self, test_db_session, test_server):
        """Test handling player join event for new player (auto-creates player)."""
        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Mock Mojang API
            with patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_111",
            ):
                # Create event dispatcher and player manager
                dispatcher = EventDispatcher()
                PlayerManager(dispatcher)

                # Create player joined event for new player
                join_time = datetime.now(timezone.utc)
                event = PlayerJoinedEvent(
                    server_id="test_server",
                    player_name="BrandNewPlayer",
                    timestamp=join_time,
                )

                # Dispatch event
                await dispatcher.dispatch_player_joined(event)

                # Wait for async handlers
                await asyncio.sleep(0.2)

                # Verify player was created
                result = await test_db_session.execute(
                    select(Player).where(Player.current_name == "BrandNewPlayer")
                )
                player = result.scalar_one_or_none()

                assert player is not None
                assert player.uuid == "new_player_uuid_111"

                # Verify online status was created
                result = await test_db_session.execute(
                    select(PlayerOnlineStatus).where(
                        PlayerOnlineStatus.player_db_id == player.player_db_id,
                        PlayerOnlineStatus.server_db_id == test_server.id,
                    )
                )
                status = result.scalar_one_or_none()

                assert status is not None
                assert status.is_online is True

    @pytest.mark.asyncio
    async def test_handle_player_left_existing_player(
        self, test_db_session, test_server, test_player
    ):
        """Test handling player leave event for existing player."""
        # Create initial online status
        online_status = PlayerOnlineStatus(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            is_online=True,
            last_join=datetime.now(timezone.utc),
        )
        test_db_session.add(online_status)
        await test_db_session.commit()

        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and player manager
            dispatcher = EventDispatcher()
            PlayerManager(dispatcher)

            # Create player left event
            leave_time = datetime.now(timezone.utc)
            event = PlayerLeftEvent(
                server_id="test_server",
                player_name="TestPlayer",
                timestamp=leave_time,
                reason="Disconnected",
            )

            # Dispatch event
            await dispatcher.dispatch_player_left(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify online status was updated
            await test_db_session.refresh(online_status)
            assert online_status.is_online is False
            assert online_status.last_leave == leave_time

    @pytest.mark.asyncio
    async def test_handle_player_left_new_player(self, test_db_session, test_server):
        """Test handling player leave event for new player (auto-creates player)."""
        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Mock Mojang API
            with patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_222",
            ):
                # Create event dispatcher and player manager
                dispatcher = EventDispatcher()
                PlayerManager(dispatcher)

                # Create player left event for new player
                leave_time = datetime.now(timezone.utc)
                event = PlayerLeftEvent(
                    server_id="test_server",
                    player_name="LeavingPlayer",
                    timestamp=leave_time,
                    reason="Disconnected",
                )

                # Dispatch event
                await dispatcher.dispatch_player_left(event)

                # Wait for async handlers
                await asyncio.sleep(0.2)

                # Verify player was created
                result = await test_db_session.execute(
                    select(Player).where(Player.current_name == "LeavingPlayer")
                )
                player = result.scalar_one_or_none()

                assert player is not None
                assert player.uuid == "new_player_uuid_222"

    @pytest.mark.asyncio
    async def test_handle_server_stopping(
        self, test_db_session, test_server, test_player
    ):
        """Test handling server stopping event - marks all players offline."""
        # Create multiple online players
        player2 = Player(
            player_db_id=2,
            uuid="test_uuid_456",
            current_name="Player2",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(player2)
        await test_db_session.commit()

        # Create online statuses
        status1 = PlayerOnlineStatus(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            is_online=True,
            last_join=datetime.now(timezone.utc),
        )
        status2 = PlayerOnlineStatus(
            player_db_id=player2.player_db_id,
            server_db_id=test_server.id,
            is_online=True,
            last_join=datetime.now(timezone.utc),
        )
        test_db_session.add(status1)
        test_db_session.add(status2)
        await test_db_session.commit()

        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and player manager
            dispatcher = EventDispatcher()
            PlayerManager(dispatcher)

            # Create server stopping event
            stop_time = datetime.now(timezone.utc)
            event = ServerStoppingEvent(
                server_id="test_server",
                timestamp=stop_time,
            )

            # Dispatch event
            await dispatcher.dispatch_server_stopping(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify all players are offline
            await test_db_session.refresh(status1)
            await test_db_session.refresh(status2)

            assert status1.is_online is False
            assert status1.last_leave == stop_time
            assert status2.is_online is False
            assert status2.last_leave == stop_time

    @pytest.mark.asyncio
    async def test_server_not_found(self, test_db_session, test_player):
        """Test handling when server is not found."""
        # Mock database session and server_tracker_crud to return None
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            with patch(
                "app.players.player_manager.server_tracker_crud.get_server_db_id",
                return_value=None,
            ):
                # Create event dispatcher and player manager
                dispatcher = EventDispatcher()
                PlayerManager(dispatcher)

                # Create player joined event
                event = PlayerJoinedEvent(
                    server_id="unknown_server",
                    player_name="TestPlayer",
                    timestamp=datetime.now(timezone.utc),
                )

                # Dispatch event
                await dispatcher.dispatch_player_joined(event)

                # Wait for async handlers
                await asyncio.sleep(0.2)

                # Verify no online status was created
                result = await test_db_session.execute(select(PlayerOnlineStatus))
                statuses = result.scalars().all()

                assert len(statuses) == 0

    @pytest.mark.asyncio
    async def test_uuid_update_for_renamed_player(self, test_db_session):
        """Test that UUID discovery updates existing player name."""
        # Create initial player
        player = Player(
            player_db_id=1,
            uuid="test_uuid_123",
            current_name="OldName",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(player)
        await test_db_session.commit()

        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and player manager
            dispatcher = EventDispatcher()
            PlayerManager(dispatcher)

            # Create UUID discovered event with new name
            event = PlayerUuidDiscoveredEvent(
                server_id="test_server",
                player_name="NewName",
                uuid="test_uuid_123",  # Same UUID
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event
            await dispatcher.dispatch_player_uuid_discovered(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify player name was updated
            await test_db_session.refresh(player)
            assert player.current_name == "NewName"
            assert player.uuid == "test_uuid_123"

    @pytest.mark.asyncio
    async def test_skin_update_on_player_join_existing_player(
        self, test_db_session, test_server, test_player
    ):
        """Test that skin update event is dispatched on every player join (existing player)."""
        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and player manager
            dispatcher = EventDispatcher()
            PlayerManager(dispatcher)

            # Track skin update events
            skin_update_events = []

            async def track_skin_update(event: PlayerSkinUpdateRequestedEvent):
                skin_update_events.append(event)

            dispatcher.on_player_skin_update_requested(track_skin_update)

            # Create player joined event
            join_time = datetime.now(timezone.utc)
            event = PlayerJoinedEvent(
                server_id="test_server",
                player_name="TestPlayer",
                timestamp=join_time,
            )

            # Dispatch event
            await dispatcher.dispatch_player_joined(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify skin update event was dispatched
            assert len(skin_update_events) == 1
            assert skin_update_events[0].player_db_id == test_player.player_db_id
            assert skin_update_events[0].uuid == test_player.uuid
            assert skin_update_events[0].player_name == test_player.current_name

    @pytest.mark.asyncio
    async def test_skin_update_on_player_join_new_player(
        self, test_db_session, test_server
    ):
        """Test that skin update event is dispatched on player join (new player)."""
        # Mock database session
        with patch("app.players.player_manager.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Mock Mojang API
            with patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_222",
            ):
                # Create event dispatcher and player manager
                dispatcher = EventDispatcher()
                PlayerManager(dispatcher)

                # Track skin update events
                skin_update_events = []

                async def track_skin_update(event: PlayerSkinUpdateRequestedEvent):
                    skin_update_events.append(event)

                dispatcher.on_player_skin_update_requested(track_skin_update)

                # Create player joined event for new player
                join_time = datetime.now(timezone.utc)
                event = PlayerJoinedEvent(
                    server_id="test_server",
                    player_name="NewPlayer123",
                    timestamp=join_time,
                )

                # Dispatch event
                await dispatcher.dispatch_player_joined(event)

                # Wait for async handlers
                await asyncio.sleep(0.2)

                # Verify player was created
                result = await test_db_session.execute(
                    select(Player).where(Player.current_name == "NewPlayer123")
                )
                player = result.scalar_one_or_none()
                assert player is not None

                # Verify skin update event was dispatched
                assert len(skin_update_events) == 1
                assert skin_update_events[0].player_db_id == player.player_db_id
                assert skin_update_events[0].uuid == "new_player_uuid_222"
                assert skin_update_events[0].player_name == "NewPlayer123"
