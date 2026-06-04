from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dynamic_config.configs.players import PlayersConfig
from app.models import Base, Player, UserPublic
from app.players.skin_fetcher import PlayerProfileFetchResult
from app.routers.players.players import (
    get_player_map_profile,
    iter_player_map_profile_events,
)
from tests.players.helpers import make_offline_uuid


def _test_user() -> UserPublic:
    return UserPublic(
        id=1,
        username="test",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def test_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def test_db_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _collect_profile_stream(uuids):
    return [event async for event in iter_player_map_profile_events(uuids)]


@pytest.mark.asyncio
async def test_profile_returns_cached_player_without_mojang(test_db_session, monkeypatch):
    player = Player(
        uuid="0b4c41928eb34f0b90228e2cb2ee6fc0",
        current_name="CachedName",
        avatar_data=b"avatar",
        created_at=datetime.now(timezone.utc),
    )
    test_db_session.add(player)
    await test_db_session.commit()

    async def fail_fetch(uuid: str):
        raise AssertionError("Mojang should not be called")

    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fail_fetch,
    )

    result = await get_player_map_profile(
        "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
        _=_test_user(),
        db=test_db_session,
    )
    assert result.resolved is True
    assert result.current_name == "CachedName"
    assert result.avatar_base64 == "YXZhdGFy"


@pytest.mark.asyncio
async def test_profile_upserts_mojang_result(test_db_session, monkeypatch):
    async def fetch(uuid: str):
        return PlayerProfileFetchResult(
            name="FetchedName",
            skin_data=b"skin",
            avatar_data=b"avatar",
        )

    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fetch,
    )

    result = await get_player_map_profile(
        "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
        _=_test_user(),
        db=test_db_session,
    )
    assert result.resolved is True
    assert result.current_name == "FetchedName"
    assert result.avatar_base64 == "YXZhdGFy"

    row = (
        await test_db_session.execute(
            select(Player).where(Player.uuid == "0b4c41928eb34f0b90228e2cb2ee6fc0")
        )
    ).scalar_one()
    assert row.current_name == "FetchedName"
    assert row.avatar_data == b"avatar"


@pytest.mark.asyncio
async def test_profile_skips_ignored_mojang_name(test_db_session, monkeypatch):
    runtime_config = SimpleNamespace(
        players=PlayersConfig(ignored_name_prefixes=["bot_"])
    )
    monkeypatch.setattr("app.players.name_filters.config", runtime_config)

    async def fetch(uuid: str):
        return PlayerProfileFetchResult(
            name="BOT_MapProfile",
            skin_data=b"skin",
            avatar_data=b"avatar",
        )

    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fetch,
    )

    result = await get_player_map_profile(
        "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
        _=_test_user(),
        db=test_db_session,
    )
    assert result.resolved is False
    assert result.current_name is None

    row = (
        await test_db_session.execute(
            select(Player).where(Player.uuid == "0b4c41928eb34f0b90228e2cb2ee6fc0")
        )
    ).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_profile_returns_unresolved_when_mojang_fails(
    test_db_session,
    monkeypatch,
):
    async def fetch(uuid: str):
        return None

    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fetch,
    )

    result = await get_player_map_profile(
        "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
        _=_test_user(),
        db=test_db_session,
    )
    assert result.resolved is False
    assert result.current_name is None
    assert result.avatar_base64 is None


@pytest.mark.asyncio
async def test_profile_returns_cached_when_mojang_fails(test_db_session, monkeypatch):
    player = Player(
        uuid="0b4c41928eb34f0b90228e2cb2ee6fc0",
        current_name="CachedNoAvatar",
        created_at=datetime.now(timezone.utc),
    )
    test_db_session.add(player)
    await test_db_session.commit()

    async def fetch(uuid: str):
        return None

    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fetch,
    )

    result = await get_player_map_profile(
        "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
        _=_test_user(),
        db=test_db_session,
    )
    assert result.resolved is True
    assert result.current_name == "CachedNoAvatar"
    assert result.avatar_base64 is None


@pytest.mark.asyncio
async def test_profile_returns_unresolved_for_non_v4_uuid(test_db_session, monkeypatch):
    async def fail_fetch(uuid: str):
        raise AssertionError("Mojang should not be called")

    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fail_fetch,
    )

    uuid = make_offline_uuid("OfflinePlayer")
    result = await get_player_map_profile(
        uuid,
        _=_test_user(),
        db=test_db_session,
    )
    assert result.uuid == uuid
    assert result.resolved is False
    assert result.current_name is None


@pytest.mark.asyncio
async def test_profile_rejects_invalid_uuid(test_db_session):
    with pytest.raises(HTTPException) as exc:
        await get_player_map_profile(
            "not-a-uuid",
            _=_test_user(),
            db=test_db_session,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_profile_stream_returns_cached_players_first(
    test_db_maker,
    monkeypatch,
):
    async with test_db_maker() as session:
        session.add(
            Player(
                uuid="0b4c41928eb34f0b90228e2cb2ee6fc0",
                current_name="CachedName",
                avatar_data=b"avatar",
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    async def fail_fetch(uuid: str):
        raise AssertionError("Mojang should not be called")

    monkeypatch.setattr(
        "app.routers.players.players.get_async_session",
        test_db_maker,
    )
    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fail_fetch,
    )

    events = await _collect_profile_stream(
        ["0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0"]
    )

    assert [event["event_type"] for event in events] == ["profile", "complete"]
    profile = events[0]["profile"]
    assert profile["uuid"] == "0b4c41928eb34f0b90228e2cb2ee6fc0"
    assert profile["current_name"] == "CachedName"
    assert profile["avatar_base64"] == "YXZhdGFy"
    assert events[-1]["total"] == 1
    assert events[-1]["resolved"] == 1


@pytest.mark.asyncio
async def test_profile_stream_upserts_missing_profiles(
    test_db_maker,
    monkeypatch,
):
    async def fetch(uuid: str):
        return PlayerProfileFetchResult(
            name="FetchedName",
            skin_data=b"skin",
            avatar_data=b"avatar",
        )

    monkeypatch.setattr(
        "app.routers.players.players.get_async_session",
        test_db_maker,
    )
    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fetch,
    )

    events = await _collect_profile_stream(
        ["0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0"]
    )

    assert [event["event_type"] for event in events] == ["profile", "complete"]
    profile = events[0]["profile"]
    assert profile["current_name"] == "FetchedName"
    assert profile["avatar_base64"] == "YXZhdGFy"
    assert events[-1]["resolved"] == 1

    async with test_db_maker() as session:
        row = (
            await session.execute(
                select(Player).where(
                    Player.uuid == "0b4c41928eb34f0b90228e2cb2ee6fc0"
                )
            )
        ).scalar_one()
    assert row.current_name == "FetchedName"
    assert row.avatar_data == b"avatar"


@pytest.mark.asyncio
async def test_profile_stream_dedupes_and_skips_non_online_uuids(
    test_db_maker,
    monkeypatch,
):
    calls: list[str] = []

    async def fetch(uuid: str):
        calls.append(uuid)
        return None

    monkeypatch.setattr(
        "app.routers.players.players.get_async_session",
        test_db_maker,
    )
    monkeypatch.setattr(
        "app.routers.players.players.skin_fetcher.fetch_player_profile",
        fetch,
    )

    offline_uuid = make_offline_uuid("OfflinePlayer")
    events = await _collect_profile_stream(
        [
            "not-a-uuid",
            offline_uuid,
            offline_uuid,
            "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
            "0b4c41928eb34f0b90228e2cb2ee6fc0",
        ]
    )

    profiles = [event["profile"] for event in events if event["event_type"] == "profile"]
    assert len(profiles) == 3
    assert profiles[0]["uuid"] == "not-a-uuid"
    assert profiles[0]["resolved"] is False
    assert profiles[1]["uuid"] == offline_uuid
    assert profiles[1]["resolved"] is False
    assert profiles[2]["uuid"] == "0b4c41928eb34f0b90228e2cb2ee6fc0"
    assert profiles[2]["resolved"] is False
    assert calls == ["0b4c41928eb34f0b90228e2cb2ee6fc0"]
    assert events[-1]["event_type"] == "complete"
    assert events[-1]["total"] == 3
