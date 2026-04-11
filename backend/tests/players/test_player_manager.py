"""Tests for player tracking functions."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Player, PlayerSession, Server, ServerStatus
from app.players.crud import upsert_player
from app.players.tracking import (
    close_server_sessions,
    process_player_join,
    process_player_left,
    update_player_skin,
)


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


def _mock_get_async_session(test_db_session):
    """Create a mock for get_async_session that yields the test session."""

    @asynccontextmanager
    async def _session_ctx():
        yield test_db_session

    return _session_ctx


class TestUpsertPlayer:
    """Test upsert_player (UUID discovered replacement)."""

    @pytest.mark.asyncio
    async def test_upsert_creates_new_player(self, test_db_session):
        """Test that upsert_player creates a new player record."""
        await upsert_player(test_db_session, "discovered_uuid_999", "NewPlayer")

        result = await test_db_session.execute(
            select(Player).where(Player.uuid == "discovered_uuid_999")
        )
        player = result.scalar_one_or_none()

        assert player is not None
        assert player.current_name == "NewPlayer"
        assert player.uuid == "discovered_uuid_999"

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_player_name(self, test_db_session):
        """Test that upsert_player updates the name for an existing UUID."""
        player = Player(
            player_db_id=1,
            uuid="test_uuid_123",
            current_name="OldName",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(player)
        await test_db_session.commit()

        await upsert_player(test_db_session, "test_uuid_123", "NewName")

        await test_db_session.refresh(player)
        assert player.current_name == "NewName"
        assert player.uuid == "test_uuid_123"


class TestProcessPlayerJoin:
    """Test process_player_join tracking function."""

    @pytest.mark.asyncio
    async def test_existing_player_creates_session(
        self, test_db_session, test_server, test_player
    ):
        """Test that joining with an existing player creates a session."""
        mock_session = _mock_get_async_session(test_db_session)

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch("app.players.tracking.update_player_skin", new_callable=AsyncMock),
        ):
            join_time = datetime.now(timezone.utc)
            await process_player_join("test_server", "TestPlayer", timestamp=join_time)

        result = await test_db_session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == test_player.player_db_id,
                PlayerSession.server_db_id == test_server.id,
                PlayerSession.left_at == None,  # noqa: E711
            )
        )
        session = result.scalar_one_or_none()

        assert session is not None
        assert session.joined_at == join_time

    @pytest.mark.asyncio
    async def test_new_player_creates_player_and_session(
        self, test_db_session, test_server
    ):
        """Test that joining with a new player auto-creates the player and session."""
        mock_session = _mock_get_async_session(test_db_session)

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_111",
            ),
            patch("app.players.tracking.update_player_skin", new_callable=AsyncMock),
        ):
            join_time = datetime.now(timezone.utc)
            await process_player_join(
                "test_server", "BrandNewPlayer", timestamp=join_time
            )

        result = await test_db_session.execute(
            select(Player).where(Player.current_name == "BrandNewPlayer")
        )
        player = result.scalar_one_or_none()

        assert player is not None
        assert player.uuid == "new_player_uuid_111"

        result = await test_db_session.execute(
            select(PlayerSession).where(
                PlayerSession.player_db_id == player.player_db_id,
                PlayerSession.server_db_id == test_server.id,
                PlayerSession.left_at == None,  # noqa: E711
            )
        )
        session = result.scalar_one_or_none()
        assert session is not None

    @pytest.mark.asyncio
    async def test_skin_update_scheduled_for_existing_player(
        self, test_db_session, test_server, test_player
    ):
        """Test that skin update task is created on player join (existing player)."""
        mock_session = _mock_get_async_session(test_db_session)
        mock_skin_update = AsyncMock()

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch("app.players.tracking.update_player_skin", mock_skin_update),
        ):
            join_time = datetime.now(timezone.utc)
            await process_player_join("test_server", "TestPlayer", timestamp=join_time)

        mock_skin_update.assert_called_once_with(
            test_player.player_db_id, test_player.uuid, test_player.current_name
        )

    @pytest.mark.asyncio
    async def test_skin_update_scheduled_for_new_player(
        self, test_db_session, test_server
    ):
        """Test that skin update task is created on player join (new player)."""
        mock_session = _mock_get_async_session(test_db_session)
        mock_skin_update = AsyncMock()

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_222",
            ),
            patch("app.players.tracking.update_player_skin", mock_skin_update),
        ):
            join_time = datetime.now(timezone.utc)
            await process_player_join(
                "test_server", "NewPlayer123", timestamp=join_time
            )

        result = await test_db_session.execute(
            select(Player).where(Player.current_name == "NewPlayer123")
        )
        player = result.scalar_one_or_none()
        assert player is not None

        mock_skin_update.assert_called_once_with(
            player.player_db_id, "new_player_uuid_222", "NewPlayer123"
        )


class TestProcessPlayerLeft:
    """Test process_player_left tracking function."""

    @pytest.mark.asyncio
    async def test_existing_player_session_ended(
        self, test_db_session, test_server, test_player
    ):
        """Test that leaving ends an existing open session."""
        join_time = datetime.now(timezone.utc)
        player_session = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=join_time,
            left_at=None,
            duration_seconds=None,
        )
        test_db_session.add(player_session)
        await test_db_session.commit()

        mock_session = _mock_get_async_session(test_db_session)

        with patch("app.players.tracking.get_async_session", mock_session):
            leave_time = datetime.now(timezone.utc)
            await process_player_left(
                "test_server",
                "TestPlayer",
                reason="Disconnected",
                timestamp=leave_time,
            )

        await test_db_session.refresh(player_session)
        assert player_session.left_at == leave_time
        assert player_session.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_new_player_auto_created_on_leave(self, test_db_session, test_server):
        """Test that leaving with a new player auto-creates the player record."""
        mock_session = _mock_get_async_session(test_db_session)

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch(
                "app.players.crud.player.fetch_player_uuid_from_mojang",
                return_value="new_player_uuid_222",
            ),
        ):
            leave_time = datetime.now(timezone.utc)
            await process_player_left(
                "test_server",
                "LeavingPlayer",
                reason="Disconnected",
                timestamp=leave_time,
            )

        result = await test_db_session.execute(
            select(Player).where(Player.current_name == "LeavingPlayer")
        )
        player = result.scalar_one_or_none()

        assert player is not None
        assert player.uuid == "new_player_uuid_222"


class TestCloseServerSessions:
    """Test close_server_sessions tracking function."""

    @pytest.mark.asyncio
    async def test_all_sessions_ended_on_server_stop(
        self, test_db_session, test_server, test_player
    ):
        """Test that all open sessions are ended when a server stops."""
        player2 = Player(
            player_db_id=2,
            uuid="test_uuid_456",
            current_name="Player2",
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(player2)
        await test_db_session.commit()

        join_time = datetime.now(timezone.utc)
        session1 = PlayerSession(
            player_db_id=test_player.player_db_id,
            server_db_id=test_server.id,
            joined_at=join_time,
            left_at=None,
            duration_seconds=None,
        )
        session2 = PlayerSession(
            player_db_id=player2.player_db_id,
            server_db_id=test_server.id,
            joined_at=join_time,
            left_at=None,
            duration_seconds=None,
        )
        test_db_session.add(session1)
        test_db_session.add(session2)
        await test_db_session.commit()

        mock_session = _mock_get_async_session(test_db_session)

        with patch("app.players.tracking.get_async_session", mock_session):
            stop_time = datetime.now(timezone.utc)
            await close_server_sessions("test_server", timestamp=stop_time)

        await test_db_session.refresh(session1)
        await test_db_session.refresh(session2)

        assert session1.left_at == stop_time
        assert session1.duration_seconds is not None
        assert session2.left_at == stop_time
        assert session2.duration_seconds is not None


class TestServerNotFound:
    """Test behavior when the server is not found in the database."""

    @pytest.mark.asyncio
    async def test_join_with_unknown_server_creates_no_session(
        self, test_db_session, test_player
    ):
        """Test that joining on an unknown server creates no session."""
        mock_session = _mock_get_async_session(test_db_session)

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch(
                "app.players.tracking.get_server_db_id",
                return_value=None,
            ),
        ):
            await process_player_join(
                "unknown_server",
                "TestPlayer",
                timestamp=datetime.now(timezone.utc),
            )

        result = await test_db_session.execute(select(PlayerSession))
        sessions = result.scalars().all()

        assert len(sessions) == 0


class TestUpdatePlayerSkin:
    """Test update_player_skin tracking function."""

    @pytest.mark.asyncio
    async def test_skin_fetched_and_saved(self, test_db_session, test_player):
        """Test that skin data is fetched and persisted."""
        mock_session = _mock_get_async_session(test_db_session)
        fake_skin = b"skin_png_data"
        fake_avatar = b"avatar_png_data"

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch(
                "app.players.tracking.skin_fetcher.fetch_player_skin",
                return_value=(fake_skin, fake_avatar),
            ),
        ):
            await update_player_skin(
                test_player.player_db_id, test_player.uuid, test_player.current_name
            )

        await test_db_session.refresh(test_player)
        assert test_player.skin_data == fake_skin
        assert test_player.avatar_data == fake_avatar
        assert test_player.last_skin_update is not None

    @pytest.mark.asyncio
    async def test_skin_fetch_failure_leaves_player_unchanged(
        self, test_db_session, test_player
    ):
        """Test that a failed skin fetch does not modify the player."""
        mock_session = _mock_get_async_session(test_db_session)

        with (
            patch("app.players.tracking.get_async_session", mock_session),
            patch(
                "app.players.tracking.skin_fetcher.fetch_player_skin",
                return_value=None,
            ),
        ):
            await update_player_skin(
                test_player.player_db_id, test_player.uuid, test_player.current_name
            )

        await test_db_session.refresh(test_player)
        assert test_player.skin_data is None
        assert test_player.avatar_data is None
        assert test_player.last_skin_update is None
