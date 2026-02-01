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
    async def test_handle_achievement_unknown_player_skipped(
        self, test_db_session, test_server
    ):
        """Test handling achievement from unknown player (should be skipped, not create player)."""
        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and chat tracker
            dispatcher = EventDispatcher()
            ChatTracker(dispatcher)

            # Create achievement event for unknown player
            event = PlayerAchievementEvent(
                server_id="test_server",
                player_name="UnknownPlayer",
                achievement_name="Kill Ender Dragon",
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event
            await dispatcher.dispatch_player_achievement(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify player was NOT created
            result = await test_db_session.execute(
                select(Player).where(Player.current_name == "UnknownPlayer")
            )
            player = result.scalar_one_or_none()

            assert player is None

            # Verify achievement was NOT saved
            result = await test_db_session.execute(select(PlayerAchievement))
            achievements = result.scalars().all()

            assert len(achievements) == 0

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
        # Mock database session and server_crud to return None
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

    @pytest.mark.asyncio
    async def test_handle_achievement_with_title(self, test_db_session, test_server):
        """Test handling achievement from player with title (e.g., 'PlayerName the Ugly')."""
        # Create a test player
        player = Player(
            player_db_id=10,
            uuid="test_uuid_with_title",
            current_name="___Astesia",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(player)
        await test_db_session.commit()

        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and chat tracker
            dispatcher = EventDispatcher()
            ChatTracker(dispatcher)

            # Create achievement event with title in player name
            event = PlayerAchievementEvent(
                server_id="test_server",
                player_name="___Astesia the Ugly",  # Player name with title
                achievement_name="Dragon Growth Hormone",
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event
            await dispatcher.dispatch_player_achievement(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify achievement was saved for the correct player
            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 1
            assert achievements[0].achievement_name == "Dragon Growth Hormone"
            assert achievements[0].player_db_id == player.player_db_id
            assert achievements[0].server_db_id == test_server.id

    @pytest.mark.asyncio
    async def test_handle_achievement_longest_name_match_priority(
        self, test_db_session, test_server
    ):
        """Test that longest player name is matched first to avoid partial matches."""
        # Create two players where one name contains the other
        short_player = Player(
            player_db_id=20,
            uuid="short_uuid",
            current_name="Steve",
            created_at=datetime.now(timezone.utc),
        )
        long_player = Player(
            player_db_id=21,
            uuid="long_uuid",
            current_name="SteveTheGreat",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(short_player)
        test_db_session.add(long_player)
        await test_db_session.commit()

        # Mock database session
        with patch("app.players.chat_tracker.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            # Create event dispatcher and chat tracker
            dispatcher = EventDispatcher()
            ChatTracker(dispatcher)

            # Create achievement event with the longer name
            event = PlayerAchievementEvent(
                server_id="test_server",
                player_name="SteveTheGreat the Mighty",  # Contains both names
                achievement_name="Epic Achievement",
                timestamp=datetime.now(timezone.utc),
            )

            # Dispatch event
            await dispatcher.dispatch_player_achievement(event)

            # Wait for async handlers
            await asyncio.sleep(0.2)

            # Verify achievement was saved for the LONGER player name
            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == long_player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 1
            assert achievements[0].achievement_name == "Epic Achievement"

            # Verify no achievement for the shorter player name
            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == short_player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 0
