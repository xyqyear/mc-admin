import json
from pathlib import Path

import pytest

from app.players.identity_resolver import (
    PlayerIdentity,
    resolve_player_by_name,
    resolve_player_by_uuid,
)
from tests.players.helpers import make_offline_uuid, make_online_uuid


class _FakeInstance:
    def __init__(self, data_path: Path):
        self._data_path = data_path

    def get_data_path(self) -> Path:
        return self._data_path


def _mock_usercache(monkeypatch, tmp_path: Path, entries) -> Path:
    data_path = tmp_path / "data"
    data_path.mkdir()
    (data_path / "usercache.json").write_text(
        json.dumps(entries),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.players.identity_resolver.docker_mc_manager.get_instance",
        lambda server_id: _FakeInstance(data_path),
    )
    return data_path


@pytest.mark.asyncio
async def test_resolve_name_prefers_usercache(monkeypatch, tmp_path):
    uuid = make_online_uuid("Steve")
    _mock_usercache(monkeypatch, tmp_path, [{"name": "Steve", "uuid": uuid}])

    async def fail_fetch(player_name: str):
        raise AssertionError("Mojang should not be called")

    monkeypatch.setattr(
        "app.players.mojang_api.fetch_player_uuid_from_mojang",
        fail_fetch,
    )

    identity = await resolve_player_by_name("server1", "Steve")

    assert identity == PlayerIdentity(uuid=uuid, name="Steve")


@pytest.mark.asyncio
async def test_resolve_name_accepts_extra_usercache_fields(monkeypatch, tmp_path):
    uuid = make_online_uuid("Steve")
    _mock_usercache(
        monkeypatch,
        tmp_path,
        [{"name": "Steve", "uuid": uuid, "expiresOn": "2099-01-01 00:00:00 +0000"}],
    )

    identity = await resolve_player_by_name("server1", "Steve")

    assert identity == PlayerIdentity(uuid=uuid, name="Steve")


@pytest.mark.asyncio
async def test_resolve_name_blocks_mojang_for_usercache_non_v4(
    monkeypatch,
    tmp_path,
):
    _mock_usercache(
        monkeypatch,
        tmp_path,
        [{"name": "Steve", "uuid": make_offline_uuid("Steve")}],
    )
    called = False

    async def fetch_uuid(player_name: str):
        nonlocal called
        called = True
        return make_online_uuid(player_name)

    monkeypatch.setattr(
        "app.players.mojang_api.fetch_player_uuid_from_mojang",
        fetch_uuid,
    )

    identity = await resolve_player_by_name("server1", "Steve")

    assert identity is None
    assert called is False


@pytest.mark.asyncio
async def test_resolve_name_falls_back_to_mojang_when_cache_missing(
    monkeypatch,
    tmp_path,
):
    _mock_usercache(monkeypatch, tmp_path, [])

    async def fetch_uuid(player_name: str):
        return make_online_uuid(player_name)

    monkeypatch.setattr(
        "app.players.mojang_api.fetch_player_uuid_from_mojang",
        fetch_uuid,
    )

    identity = await resolve_player_by_name("server1", "Alex")

    assert identity == PlayerIdentity(uuid=make_online_uuid("Alex"), name="Alex")


@pytest.mark.asyncio
async def test_resolve_uuid_prefers_usercache(monkeypatch, tmp_path):
    uuid = make_online_uuid("Alex")
    _mock_usercache(monkeypatch, tmp_path, [{"name": "Alex", "uuid": uuid}])

    async def fail_fetch(uuid: str):
        raise AssertionError("Mojang should not be called")

    monkeypatch.setattr(
        "app.players.mojang_api.fetch_player_name_from_mojang",
        fail_fetch,
    )

    identity = await resolve_player_by_uuid("server1", uuid)

    assert identity == PlayerIdentity(uuid=uuid, name="Alex")


@pytest.mark.asyncio
async def test_resolve_uuid_blocks_non_v4_before_mojang(monkeypatch, tmp_path):
    _mock_usercache(monkeypatch, tmp_path, [])
    called = False

    async def fetch_name(uuid: str):
        nonlocal called
        called = True
        return "OfflinePlayer"

    monkeypatch.setattr(
        "app.players.mojang_api.fetch_player_name_from_mojang",
        fetch_name,
    )

    identity = await resolve_player_by_uuid(
        "server1",
        make_offline_uuid("OfflinePlayer"),
    )

    assert identity is None
    assert called is False
