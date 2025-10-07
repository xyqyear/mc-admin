"""Tests for ChatTracker."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.events.base import PlayerAchievementEvent, PlayerChatMessageEvent
from app.events.dispatcher import EventDispatcher
from app.models import (
    Base,
    Player,
    PlayerAchievement,
    PlayerChatMessage,
    Server,
    ServerStatus,
)
from app.players.chat_tracker import ChatTracker


@pytest.fixture
async def test_db_engine():
    """Create a temporary in-memory SQLite database for testing."""
    # Create temporary in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
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


@pytest.fixture
def mock_mojang_api():
    """Mock the Mojang API."""
    with patch("app.players.crud.player.fetch_player_uuid_from_mojang") as mock:
        # Simply return the value directly in async context
        async def return_uuid(*args, **kwargs):
            return "new_player_uuid_456"

        mock.side_effect = return_uuid
        yield mock


class TestChatTracker:
    """Test ChatTracker functionality."""

    @pytest.mark.asyncio
    async def test_handle_chat_message_existing_player(
        self, test_db_session, test_server, test_player
    ):
        """Test handling chat message from existing player."""
        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and chat tracker
            dispatcher = EventDispatcher()
            ChatTracker(dispatcher)

            # Create chat message event
            event = PlayerChatMessageEvent(
                server_id="test_server",
                player_name="TestPlayer",
                message="Hello world!",
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event
            await dispatcher.dispatch_player_chat_message(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify chat message was saved
            result = await test_db_session.execute(
                select(PlayerChatMessage).where(
                    PlayerChatMessage.player_db_id == test_player.player_db_id
                )
            )
            messages = result.scalars().all()

            assert len(messages) == 1
            assert messages[0].message_text == "Hello world!"
            assert messages[0].player_db_id == test_player.player_db_id
            assert messages[0].server_db_id == test_server.id

    @pytest.mark.asyncio
    async def test_handle_chat_message_new_player(
        self, test_db_session, test_server, mock_mojang_api
    ):
        """Test handling chat message from new player (auto-creates player)."""
        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Mock Mojang API
            with patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_456",
            ):
                # Create event dispatcher and chat tracker
                dispatcher = EventDispatcher()
                ChatTracker(dispatcher)

                # Create chat message event for new player
                event = PlayerChatMessageEvent(
                    server_id="test_server",
                    player_name="NewPlayer",
                    message="First message!",
                    timestamp=datetime.now(timezone.utc),
                )

                # Dispatch event
                await dispatcher.dispatch_player_chat_message(event)

                # Wait for async handlers
                await asyncio.sleep(0.2)

                # Verify player was created
                result = await test_db_session.execute(
                    select(Player).where(Player.current_name == "NewPlayer")
                )
                player = result.scalar_one_or_none()

                assert player is not None
                assert player.uuid == "new_player_uuid_456"

                # Verify chat message was saved
                result = await test_db_session.execute(
                    select(PlayerChatMessage).where(
                        PlayerChatMessage.player_db_id == player.player_db_id
                    )
                )
                messages = result.scalars().all()

                assert len(messages) == 1
                assert messages[0].message_text == "First message!"

    @pytest.mark.asyncio
    async def test_handle_achievement_existing_player(
        self, test_db_session, test_server, test_player
    ):
        """Test handling achievement from existing player."""
        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and chat tracker
            dispatcher = EventDispatcher()
            ChatTracker(dispatcher)

            # Create achievement event
            event = PlayerAchievementEvent(
                server_id="test_server",
                player_name="TestPlayer",
                achievement_name="Mine Diamond",
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event
            await dispatcher.dispatch_player_achievement(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify achievement was saved
            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == test_player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 1
            assert achievements[0].achievement_name == "Mine Diamond"
            assert achievements[0].player_db_id == test_player.player_db_id
            assert achievements[0].server_db_id == test_server.id

    @pytest.mark.asyncio
    async def test_handle_achievement_new_player(self, test_db_session, test_server):
        """Test handling achievement from new player (auto-creates player)."""
        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Mock Mojang API
            with patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_789",
            ):
                # Create event dispatcher and chat tracker
                dispatcher = EventDispatcher()
                ChatTracker(dispatcher)

                # Create achievement event for new player
                event = PlayerAchievementEvent(
                    server_id="test_server",
                    player_name="AnotherPlayer",
                    achievement_name="Kill Ender Dragon",
                    timestamp=datetime.now(timezone.utc),
                )

                # Dispatch event
                await dispatcher.dispatch_player_achievement(event)

                # Wait for async handlers
                await asyncio.sleep(0.2)

                # Verify player was created
                result = await test_db_session.execute(
                    select(Player).where(Player.current_name == "AnotherPlayer")
                )
                player = result.scalar_one_or_none()

                assert player is not None
                assert player.uuid == "new_player_uuid_789"

                # Verify achievement was saved
                result = await test_db_session.execute(
                    select(PlayerAchievement).where(
                        PlayerAchievement.player_db_id == player.player_db_id
                    )
                )
                achievements = result.scalars().all()

                assert len(achievements) == 1
                assert achievements[0].achievement_name == "Kill Ender Dragon"

    @pytest.mark.asyncio
    async def test_duplicate_achievement_not_saved(
        self, test_db_session, test_server, test_player
    ):
        """Test that duplicate achievements are not saved."""
        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and chat tracker
            dispatcher = EventDispatcher()
            ChatTracker(dispatcher)

            # Create achievement event
            event = PlayerAchievementEvent(
                server_id="test_server",
                player_name="TestPlayer",
                achievement_name="Mine Diamond",
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event twice
            await dispatcher.dispatch_player_achievement(event)
            await asyncio.sleep(0.2)
            await dispatcher.dispatch_player_achievement(event)
            await asyncio.sleep(0.2)

            # Verify only one achievement was saved
            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == test_player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 1

    @pytest.mark.asyncio
    async def test_server_not_found(self, test_db_session, test_player):
        """Test handling when server is not found."""
        # Mock database session and server_tracker_crud to return None
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            with patch(
                "app.players.chat_tracker.get_server_db_id",
                return_value=None,
            ):
                # Create event dispatcher and chat tracker
                dispatcher = EventDispatcher()
                ChatTracker(dispatcher)

                # Create chat message event
                event = PlayerChatMessageEvent(
                    server_id="unknown_server",
                    player_name="TestPlayer",
                    message="Hello!",
                    timestamp=datetime.now(timezone.utc),
                )

                # Dispatch event
                await dispatcher.dispatch_player_chat_message(event)

                # Wait for async handlers
                await asyncio.sleep(0.2)

                # Verify no chat message was saved
                result = await test_db_session.execute(select(PlayerChatMessage))
                messages = result.scalars().all()

                assert len(messages) == 0
