import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth.schemas import UserPublic
from app.dependencies import get_current_user
from app.dynamic_config.configs.players import PlayersConfig
from app.main import api_app
from app.players.models import Player
from app.players.skin_fetcher import PlayerProfileFetchResult
from app.routers.players.players import (
    get_player_map_profile,
    iter_player_map_profile_events,
)
from app.runtime_resources import current_runtime
from tests.players.helpers import make_offline_uuid
from tests.support.runtime import set_runtime_resource


def _test_user() -> UserPublic:
    return UserPublic(
        id=1,
        username="test",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
async def test_db_session(db_session):
    return db_session


@pytest.fixture
async def test_db_maker(db_session_factory):
    return db_session_factory


async def _collect_profile_stream(uuids):
    return [event async for event in iter_player_map_profile_events(uuids)]


@pytest.mark.asyncio
async def test_profile_returns_cached_player_without_mojang(test_db_session, monkeypatch):
    player = Player(
        uuid="0b4c41928eb34f0b90228e2cb2ee6fc0",
        current_name="CachedName",
        avatar_data=b"avatar",
        created_at=datetime.now(UTC),
    )
    test_db_session.add(player)
    await test_db_session.commit()

    async def fail_fetch(uuid: str):
        raise AssertionError("Mojang should not be called")

    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fail_fetch)

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

    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fetch)

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
    set_runtime_resource(monkeypatch, 'dynamic_configuration', runtime_config)

    async def fetch(uuid: str):
        return PlayerProfileFetchResult(
            name="BOT_MapProfile",
            skin_data=b"skin",
            avatar_data=b"avatar",
        )

    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fetch)

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

    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fetch)

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
        created_at=datetime.now(UTC),
    )
    test_db_session.add(player)
    await test_db_session.commit()

    async def fetch(uuid: str):
        return None

    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fetch)

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

    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fail_fetch)

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
async def test_profile_stream_preserves_nullable_fields_for_mixed_players(
    db_session_factory, monkeypatch,
):
    cached_uuid = "0b4c41928eb34f0b90228e2cb2ee6fc0"
    partial_uuid = "123e4567e89b42d3a456426614174000"
    offline_uuid = make_offline_uuid("OfflinePlayer")
    async with db_session_factory() as session:
        session.add_all([
            Player(uuid=cached_uuid, current_name="CachedName", avatar_data=b"avatar", created_at=datetime.now(UTC)),
            Player(uuid=partial_uuid, current_name="KnownWithoutAvatar", created_at=datetime.now(UTC)),
        ])
        await session.commit()

    fetched = []

    async def unavailable_profile(uuid: str):
        fetched.append(uuid)

    monkeypatch.setattr(current_runtime().skin_fetcher, "fetch_player_profile", unavailable_profile)
    monkeypatch.setitem(api_app.dependency_overrides, get_current_user, _test_user)
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        response = await client.post("/players/profiles/stream", json={
            "uuids": [cached_uuid.upper(), partial_uuid, offline_uuid, cached_uuid, "invalid"],
        })
    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: "))
              for line in response.text.splitlines() if line.startswith("data: ")]
    profiles = {event["profile"]["uuid"]: event["profile"]
                for event in events if event["event_type"] == "profile"}
    assert len(profiles) == 4
    for uuid in ["invalid", offline_uuid]:
        assert profiles[uuid] == {
            "uuid": uuid, "resolved": False, "player_db_id": None,
            "current_name": None, "avatar_base64": None, "last_skin_update": None,
        }
    assert profiles[cached_uuid]["current_name"] == "CachedName"
    assert profiles[cached_uuid]["avatar_base64"] == "YXZhdGFy"
    assert profiles[cached_uuid]["last_skin_update"] is None
    assert profiles[partial_uuid]["current_name"] == "KnownWithoutAvatar"
    assert profiles[partial_uuid]["avatar_base64"] is None
    assert profiles[partial_uuid]["last_skin_update"] is None
    assert all(profiles[uuid]["resolved"] for uuid in [cached_uuid, partial_uuid])
    assert fetched == [partial_uuid]
    assert events[-1] == {"event_type": "complete", "total": 4, "resolved": 2}


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
    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fetch)

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

    monkeypatch.setattr(
        "app.routers.players.players.get_async_session",
        test_db_maker,
    )
    monkeypatch.setattr(current_runtime().skin_fetcher, 'fetch_player_profile', fetch)

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


async def test_profile_stream_reports_safe_error_and_drains_other_fetches(
    test_db_maker, monkeypatch, caplog,
):
    first = "0b4c41928eb34f0b90228e2cb2ee6fc0"
    second = "123e4567e89b42d3a456426614174000"
    async with test_db_maker() as db:
        db.add(Player(uuid=first, current_name="已缓存玩家", created_at=datetime.now(UTC)))
        await db.commit()
    active_sessions = 0

    @asynccontextmanager
    async def short_session():
        nonlocal active_sessions
        active_sessions += 1
        try:
            async with test_db_maker() as db:
                yield db
        finally:
            active_sessions -= 1

    other_started = asyncio.Event()
    other_cancelled = asyncio.Event()
    secret = "https://profile.invalid/?token=private-stream-token&password=private-password"

    async def fetch(uuid: str):
        assert active_sessions == 0
        if uuid == first:
            await asyncio.wait_for(other_started.wait(), 2)
            raise RuntimeError(secret)
        other_started.set()
        try:
            await asyncio.Future()
        finally:
            other_cancelled.set()

    monkeypatch.setattr("app.routers.players.players.get_async_session", short_session)
    monkeypatch.setattr(current_runtime().skin_fetcher, "fetch_player_profile", fetch)
    monkeypatch.setitem(api_app.dependency_overrides, get_current_user, _test_user)
    with caplog.at_level(logging.ERROR):
        async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
            response = await client.post("/players/profiles/stream", json={"uuids": [first, second]})
    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: "))
              for line in response.text.splitlines() if line.startswith("data: ")]
    assert [event["event_type"] for event in events] == ["profile", "error"]
    assert events[0]["profile"]["current_name"] == "已缓存玩家"
    assert events[-1] == {"event_type": "error", "message": "玩家资料加载失败，请重试"}
    assert other_cancelled.is_set()
    assert active_sessions == 0
    assert "private-stream-token" not in response.text + caplog.text
    assert "private-password" not in response.text + caplog.text
    assert "profile.invalid" not in response.text + caplog.text
    records = [record for record in caplog.records if "Player profile stream failed" in record.message]
    assert len(records) == 1
    assert records[0].exc_info is None
    assert "RuntimeError" in records[0].message
