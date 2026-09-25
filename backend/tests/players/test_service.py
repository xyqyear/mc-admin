"""Player producers share persistence and publish only committed observations."""
import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy import delete, select

from app.db.metadata import Base
from app.dynamic_config import get_config
from app.events import ChatEvent, PlayerJoinEvent, PlayerLeaveEvent, ServerStoppingEvent
from app.log_monitor import LogMonitor
from app.log_monitor.events import PlayerJoinedEvent
from app.minecraft import MCServerStatus
from app.players import get_player_service
from app.players.heartbeat import HeartbeatManager
from app.players.models import Player, PlayerChatMessage, PlayerSession
from app.players.player_syncer import PlayerSyncer
from app.runtime_resources import current_runtime
from app.servers.models import Server, ServerStatus
from tests.players.helpers import make_online_uuid
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def tracking_system(isolated_runtime, tmp_path, monkeypatch):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await runtime.resource("config_manager").initialize_all_configs()
    db = runtime.database.session_factory
    now = datetime.now(UTC)
    async with db() as session:
        server = Server(server_id="observed", status=ServerStatus.ACTIVE, created_at=now, updated_at=now)
        session.add(server)
        await session.commit()
        generation = server.id

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("app.players.identity_resolver._usercache_path", lambda _: data / "usercache.json")
    mojang = AsyncMock(side_effect=AssertionError("unexpected Mojang fallback"))
    monkeypatch.setattr("app.players.mojang_api.fetch_player_uuid_from_mojang", mojang)
    service = get_player_service()
    events = []
    order = []
    database_path = runtime.database.engine.url.database

    def publish(event):
        with closing(sqlite3.connect(database_path)) as connection, connection:
            if isinstance(event, ChatEvent):
                assert connection.execute("SELECT message_text FROM player_chat_message WHERE message_id = ?", (int(event.cursor),)).fetchone() == (event.message,)
            elif isinstance(event, PlayerJoinEvent):
                assert connection.execute("SELECT COUNT(*) FROM player_session WHERE player_db_id = ? AND left_at IS NULL", (event.player.player_db_id,)).fetchone() == (1,)
            elif isinstance(event, (PlayerLeaveEvent, ServerStoppingEvent)):
                assert connection.execute("SELECT COUNT(*) FROM player_session WHERE left_at IS NULL").fetchone() == (0,)
        events.append(event)
        order.append(event.type)

    async def skin(uuid):
        order.append("skin")
        return (b"owned-skin", b"owned-avatar")

    monkeypatch.setattr(service, "publish", publish)
    monkeypatch.setattr(service, "clock", lambda: now)
    monkeypatch.setattr(service.skin_client, "fetch_player_skin", AsyncMock(side_effect=skin))
    yield SimpleNamespace(runtime=runtime, service=service, db=db, data=data, events=events, order=order, now=now, generation=generation, mojang=mojang)
    await runtime.close()


async def test_log_tail_commits_in_order_and_preserves_chat_cursor(tracking_system):
    system = tracking_system
    uuid = make_online_uuid("ObservedPlayer")
    log = system.data / "latest.log"
    old = "[10:00:00] [Server thread/INFO]: <ObservedPlayer> retained old line\n"
    log.write_text(old)
    monitor = LogMonitor(players=system.service)
    monitor._file_pointers["observed"] = len(old.encode())
    lines = [
        f"[10:00:01] [User Authenticator/INFO]: UUID of player ObservedPlayer is {UUID(uuid)}",
        "[10:00:02] [Server thread/INFO]: ObservedPlayer[/127.0.0.1:42] logged in with entity id 2",
        "[10:00:03] [Server thread/INFO]: <ObservedPlayer> 新消息",
        "[10:00:04] [Server thread/INFO]: ObservedPlayer lost connection: Disconnected",
        "[10:00:05] [Server thread/INFO]: Stopping server",
    ]
    log.write_text(old + "\n".join(lines) + "\n")
    await monitor._process_log_changes("observed", log)
    await monitor._process_log_changes("observed", log)
    assert [event.type for event in system.events] == ["player_join", "chat", "player_leave", "server_stopping"]
    assert system.order.index("skin") > system.order.index("player_join")
    assert monitor._file_pointers["observed"] == log.stat().st_size
    first_chat = next(event for event in system.events if isinstance(event, ChatEvent))
    async with system.db() as session:
        assert (await session.scalars(select(PlayerChatMessage.message_text))).all() == ["新消息"]
        await session.execute(delete(PlayerChatMessage))
        await session.commit()
    await system.service.record_chat_message("observed", "ObservedPlayer", "after cleanup")
    assert isinstance(system.events[-1], ChatEvent)
    assert int(system.events[-1].cursor) > int(first_chat.cursor)
    system.mojang.assert_not_awaited()


async def test_log_and_rcon_share_one_session_with_independent_connections(tracking_system, monkeypatch):
    system = tracking_system
    uuid = make_online_uuid("ObservedPlayer")
    (system.data / "usercache.json").write_text(json.dumps([{"name": "ObservedPlayer", "uuid": str(UUID(uuid))}]))
    monitor = LogMonitor(players=system.service)
    syncer = PlayerSyncer(players=system.service)
    instance = MagicMock()
    instance.get_status = AsyncMock(return_value=MCServerStatus.HEALTHY)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def list_players():
        entered.set()
        await release.wait()
        return ["ObservedPlayer"]

    instance.list_players = list_players
    monkeypatch.setattr(current_runtime().resource('docker_mc_manager'), 'get_instance', lambda _: instance)
    rcon = asyncio.create_task(syncer._validate_server("observed", system.generation))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        join = asyncio.create_task(monitor._handle_event(PlayerJoinedEvent(server_id="observed", player_name="ObservedPlayer", timestamp=system.now)))
        release.set()
        await asyncio.wait_for(asyncio.gather(join, rcon), 5)
    finally:
        release.set()
        await rcon
    async with system.db() as session:
        rows = (await session.scalars(select(PlayerSession))).all()
        assert len(rows) == 1
        assert rows[0].left_at is None
    await asyncio.gather(
        system.service.process_player_left("observed", "ObservedPlayer", timestamp=system.now + timedelta(seconds=50)),
        system.service.process_player_left("observed", "ObservedPlayer", timestamp=system.now + timedelta(seconds=50)),
    )
    async with system.db() as session:
        row = (await session.scalars(select(PlayerSession))).one()
        assert row.duration_seconds == 50
    system.mojang.assert_not_awaited()


async def test_crash_closes_at_heartbeat_before_rcon_reopens(tracking_system, monkeypatch):
    from app.players.crud.heartbeat import upsert_heartbeat

    system = tracking_system
    await system.service.discover_identity(make_online_uuid("ObservedPlayer"), "ObservedPlayer")
    joined = system.now - timedelta(minutes=10)
    crash = system.now - timedelta(minutes=5)
    await system.service.process_player_join("observed", "ObservedPlayer", joined)
    system.events.clear()
    async with system.db() as session:
        await upsert_heartbeat(session, crash)
    monkeypatch.setattr("app.players.heartbeat.get_async_session", system.db)
    monkeypatch.setattr(get_config().players.heartbeat, "crash_threshold_minutes", 1)

    async def resync():
        assert [event.type for event in system.events] == ["player_leave"]
        await system.service.reconcile_online("observed", system.generation, ["ObservedPlayer"])

    monkeypatch.setattr(current_runtime().resource('player_syncer'), 'validate_all_servers', resync)
    await HeartbeatManager(players=system.service)._check_crash()
    assert [event.type for event in system.events] == ["player_leave", "player_join"]
    assert system.events[0].timestamp == crash
    async with system.db() as session:
        rows = (await session.scalars(select(PlayerSession).order_by(PlayerSession.session_id))).all()
        assert len(rows) == 2
        assert rows[0].duration_seconds == 300
        assert rows[1].left_at is None


async def test_identity_gates_apply_to_log_and_rcon_producers(tracking_system, monkeypatch):
    from tests.players.helpers import make_offline_uuid

    system = tracking_system
    offline = make_offline_uuid("OfflinePlayer")
    (system.data / "usercache.json").write_text(json.dumps([{"name": "OfflinePlayer", "uuid": offline}]))
    set_runtime_resource(monkeypatch, 'dynamic_configuration', SimpleNamespace(players=SimpleNamespace(ignored_name_prefixes=["bot_"])))
    await system.service.discover_identity(offline, "OfflinePlayer")
    await system.service.discover_identity(make_online_uuid("Bot"), "BoT_Player")
    await system.service.reconcile_online("observed", system.generation, ["OfflinePlayer", "BOT_Player"])
    async with system.db() as session:
        assert (await session.scalars(select(Player))).all() == []
        assert (await session.scalars(select(PlayerSession))).all() == []
    assert system.events == []
    system.mojang.assert_not_awaited()


async def test_failed_rcon_observation_preserves_online_session(tracking_system, monkeypatch):
    system = tracking_system
    await system.service.discover_identity(make_online_uuid("ObservedPlayer"), "ObservedPlayer")
    await system.service.process_player_join("observed", "ObservedPlayer")
    instance = MagicMock()
    instance.get_status = AsyncMock(return_value=MCServerStatus.HEALTHY)
    instance.list_players = AsyncMock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr(current_runtime().resource('docker_mc_manager'), 'get_instance', lambda _: instance)
    await PlayerSyncer(players=system.service)._validate_server("observed", system.generation)
    async with system.db() as session:
        row = (await session.scalars(select(PlayerSession))).one()
        assert row.left_at is None
    assert [event.type for event in system.events] == ["player_join"]


async def test_service_dependencies_stay_with_the_owner_runtime(tracking_system, tmp_path, monkeypatch):
    from app.runtime import Runtime
    from app.runtime_resources import current_runtime

    system = tracking_system
    path = system.runtime.settings.server_path / "observed" / "data" / "usercache.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"name": "ObservedPlayer", "uuid": make_online_uuid("ObservedPlayer")}]))
    monkeypatch.setattr("app.players.identity_resolver._usercache_path", lambda server_id: current_runtime().settings.server_path / server_id / "data" / "usercache.json")
    other = Runtime(system.runtime.settings.model_copy(update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'other.sqlite3'}", "server_path": tmp_path / "other-servers"}))

    class RuntimeNameFilters:
        @property
        def players(self):
            prefixes = ["Observed"] if current_runtime() is other else []
            return SimpleNamespace(ignored_name_prefixes=prefixes)

    set_runtime_resource(monkeypatch, 'dynamic_configuration', RuntimeNameFilters())
    try:
        async with other.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        with other.bind():
            second = get_player_service()
            subscription = other.resource("event_bus").subscribe()
            assert second is not system.service
            await system.service.process_player_join("observed", "ObservedPlayer")
            assert subscription.queue.empty()
        async with system.db() as session:
            assert len((await session.scalars(select(PlayerSession))).all()) == 1
        async with other.database.session_factory() as session:
            assert (await session.scalars(select(PlayerSession))).all() == []
        assert [event.type for event in system.events] == ["player_join"]
    finally:
        await other.close()
