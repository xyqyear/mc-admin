"""Tests for record_chat_message and record_achievement tracking functions."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Player,
    PlayerAchievement,
    PlayerChatMessage,
    Server,
    ServerStatus,
)
from app.players.tracking import record_achievement, record_chat_message
from tests.players.helpers import make_offline_uuid, make_online_uuid


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
        uuid=make_online_uuid("TestPlayer"),
        current_name="TestPlayer",
        created_at=datetime.now(timezone.utc),
    )
    test_db_session.add(player)
    await test_db_session.commit()
    return player


@pytest.fixture
def mock_mojang_api():
    """Mock the Mojang API."""
    with patch("app.players.mojang_api.fetch_player_uuid_from_mojang") as mock:

        async def return_uuid(*args, **kwargs):
            return make_online_uuid("NewPlayer")

        mock.side_effect = return_uuid
        yield mock


class TestRecordChatMessage:
    """Test record_chat_message functionality."""

    @pytest.mark.asyncio
    async def test_existing_player(self, test_db_session, test_server, test_player):
        """Test recording chat message from existing player."""
        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            await record_chat_message(
                server_id="test_server",
                player_name="TestPlayer",
                message="Hello world!",
                timestamp=datetime.now(timezone.utc),
            )

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
    async def test_new_player(self, test_db_session, test_server, mock_mojang_api):
        """Test recording chat message from new player (auto-creates player)."""
        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            with patch(
                "app.players.mojang_api.fetch_player_uuid_from_mojang",
                return_value=make_online_uuid("NewPlayer"),
            ):
                await record_chat_message(
                    server_id="test_server",
                    player_name="NewPlayer",
                    message="First message!",
                    timestamp=datetime.now(timezone.utc),
                )

                result = await test_db_session.execute(
                    select(Player).where(Player.current_name == "NewPlayer")
                )
                player = result.scalar_one_or_none()

                assert player is not None
                assert player.uuid == make_online_uuid("NewPlayer")

                result = await test_db_session.execute(
                    select(PlayerChatMessage).where(
                        PlayerChatMessage.player_db_id == player.player_db_id
                    )
                )
                messages = result.scalars().all()

                assert len(messages) == 1
                assert messages[0].message_text == "First message!"

    @pytest.mark.asyncio
    async def test_server_not_found(self, test_db_session, test_player):
        """Test handling when server is not found."""
        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            with patch(
                "app.players.tracking.get_server_db_id",
                return_value=None,
            ):
                await record_chat_message(
                    server_id="unknown_server",
                    player_name="TestPlayer",
                    message="Hello!",
                    timestamp=datetime.now(timezone.utc),
                )

                result = await test_db_session.execute(select(PlayerChatMessage))
                messages = result.scalars().all()

                assert len(messages) == 0


class TestRecordAchievement:
    """Test record_achievement functionality."""

    @pytest.mark.asyncio
    async def test_existing_player(self, test_db_session, test_server, test_player):
        """Test recording achievement from existing player."""
        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            await record_achievement(
                server_id="test_server",
                player_name="TestPlayer",
                achievement_name="Mine Diamond",
                timestamp=datetime.now(timezone.utc),
            )

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
    async def test_unknown_player_skipped(self, test_db_session, test_server):
        """Test that achievement from unknown player is skipped (no player created)."""
        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            await record_achievement(
                server_id="test_server",
                player_name="UnknownPlayer",
                achievement_name="Kill Ender Dragon",
                timestamp=datetime.now(timezone.utc),
            )

            result = await test_db_session.execute(
                select(Player).where(Player.current_name == "UnknownPlayer")
            )
            player = result.scalar_one_or_none()
            assert player is None

            result = await test_db_session.execute(select(PlayerAchievement))
            achievements = result.scalars().all()
            assert len(achievements) == 0

    @pytest.mark.asyncio
    async def test_offline_uuid_player_skipped(self, test_db_session, test_server):
        player = Player(
            player_db_id=2,
            uuid=make_offline_uuid("OfflinePlayer"),
            current_name="OfflinePlayer",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(player)
        await test_db_session.commit()

        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            await record_achievement(
                server_id="test_server",
                player_name="OfflinePlayer",
                achievement_name="Not Recorded",
                timestamp=datetime.now(timezone.utc),
            )

            result = await test_db_session.execute(select(PlayerAchievement))
            achievements = result.scalars().all()
            assert len(achievements) == 0

    @pytest.mark.asyncio
    async def test_duplicate_not_saved(self, test_db_session, test_server, test_player):
        """Test that duplicate achievements are not saved."""
        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            ts = datetime.now(timezone.utc)

            await record_achievement(
                server_id="test_server",
                player_name="TestPlayer",
                achievement_name="Mine Diamond",
                timestamp=ts,
            )

            await record_achievement(
                server_id="test_server",
                player_name="TestPlayer",
                achievement_name="Mine Diamond",
                timestamp=ts,
            )

            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == test_player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 1

    @pytest.mark.asyncio
    async def test_player_with_title(self, test_db_session, test_server):
        """Test matching player with title suffix (e.g., 'PlayerName the Ugly')."""
        player = Player(
            player_db_id=10,
            uuid=make_online_uuid("___Astesia"),
            current_name="___Astesia",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(player)
        await test_db_session.commit()

        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            await record_achievement(
                server_id="test_server",
                player_name="___Astesia the Ugly",
                achievement_name="Dragon Growth Hormone",
                timestamp=datetime.now(timezone.utc),
            )

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
    async def test_longest_name_match_priority(self, test_db_session, test_server):
        """Test that longest player name is matched first to avoid partial matches."""
        short_player = Player(
            player_db_id=20,
            uuid=make_online_uuid("Steve"),
            current_name="Steve",
            created_at=datetime.now(timezone.utc),
        )
        long_player = Player(
            player_db_id=21,
            uuid=make_online_uuid("SteveTheGreat"),
            current_name="SteveTheGreat",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(short_player)
        test_db_session.add(long_player)
        await test_db_session.commit()

        with patch("app.players.tracking.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_db_session

            await record_achievement(
                server_id="test_server",
                player_name="SteveTheGreat the Mighty",
                achievement_name="Epic Achievement",
                timestamp=datetime.now(timezone.utc),
            )

            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == long_player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 1
            assert achievements[0].achievement_name == "Epic Achievement"

            result = await test_db_session.execute(
                select(PlayerAchievement).where(
                    PlayerAchievement.player_db_id == short_player.player_db_id
                )
            )
            achievements = result.scalars().all()

            assert len(achievements) == 0
