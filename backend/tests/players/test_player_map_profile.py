from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Player, UserPublic
from app.players.skin_fetcher import PlayerProfileFetchResult
from app.routers.players.players import get_player_map_profile


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
async def test_profile_rejects_invalid_uuid(test_db_session):
    with pytest.raises(HTTPException) as exc:
        await get_player_map_profile(
            "not-a-uuid",
            _=_test_user(),
            db=test_db_session,
        )
    assert exc.value.status_code == 400
