import asyncio
import os
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import select
from watchfiles import Change, awatch

from app.log_monitor.events import PlayerLeftEvent, PlayerUuidDiscoveredEvent
from app.log_monitor.monitor import LogMonitor
from app.operations.context import current_execution
from app.operations.execution import operation_scope
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.players.models import Player, PlayerChatMessage, PlayerSession
from app.runtime_resources import current_runtime
from app.servers.models import Server, ServerStatus
from tests.players.helpers import make_online_uuid


def identity_line(name):
    return f"[12:00:00] [Server thread/INFO]: UUID of player {name} is {UUID(make_online_uuid(name))}\n"


def chat_line(name, message):
    return f"[12:00:01] [Server thread/INFO]: <{name}> {message}\n"


@pytest.fixture
async def log_monitor_instance(db_session_factory, runtime_config, isolated_runtime, monkeypatch):
    async with db_session_factory() as session:
        session.add_all([Server(id=index, server_id=name, status=ServerStatus.ACTIVE)
                         for index, name in enumerate(("test_server", "other_server"), start=1)])
        await session.commit()
    monkeypatch.setattr(isolated_runtime.player_service.skin_client, "fetch_player_skin", AsyncMock(return_value=None))
    monitor = LogMonitor()
    try:
        yield monitor
    finally:
        await monitor.stop_all()


class TestLogMonitor:
    async def test_watcher_persists_player_events_after_parent_operation_finishes(
        self, log_monitor_instance, tmp_path, db_session_factory, isolated_runtime, monkeypatch,
    ):
        journal = OperationJournal(db_session_factory)
        isolated_runtime.journal = journal
        log_path = tmp_path / "latest.log"
        log_path.touch()
        observed = []
        processed = asyncio.Event()
        handle_event = log_monitor_instance._handle_event

        async def observe(event):
            observed.append((current_runtime(), current_execution()))
            await handle_event(event)
            if isinstance(event, PlayerLeftEvent):
                processed.set()

        monkeypatch.setattr(log_monitor_instance, "_handle_event", observe)
        async with operation_scope("server_create", []) as parent:
            assert parent is not None
            await log_monitor_instance._watch_server("test_server", log_path)
            async with asyncio.timeout(5):
                while "test_server" not in log_monitor_instance._file_pointers:
                    await asyncio.sleep(0)
        before = await journal.get(parent.operation_id)
        assert before is not None and before.state is OperationState.SUCCEEDED

        content = (
            identity_line("TestPlayer")
            + "[12:00:01] [Server thread/INFO]: TestPlayer[/127.0.0.1:12345] logged in with entity id 1 at (0, 0, 0)\n"
            + chat_line("TestPlayer", "父操作结束后的聊天")
            + "[12:00:02] [Server thread/INFO]: TestPlayer lost connection: Disconnected\n"
        )
        await asyncio.to_thread(log_path.write_text, content)
        await asyncio.wait_for(processed.wait(), 5)
        await log_monitor_instance.stop_watching("test_server")

        assert observed == [(isolated_runtime, None)] * 4
        async with db_session_factory() as session:
            player = (await session.scalars(select(Player))).one()
            presence = (await session.scalars(select(PlayerSession))).one()
            message = (await session.scalars(select(PlayerChatMessage))).one()
            assert player.uuid == make_online_uuid("TestPlayer")
            assert presence.player_db_id == message.player_db_id == player.player_db_id
            assert presence.server_db_id == message.server_db_id == 1
            assert presence.left_at is not None
            assert message.message_text == "父操作结束后的聊天"
        assert await journal.get(parent.operation_id) == before
        assert len(await journal.list()) == 1
        assert not log_monitor_instance.is_watching("test_server")

    async def test_appended_log_persists_identity_presence_and_chat_once(self, log_monitor_instance, tmp_path, db_session_factory):
        log_path = tmp_path / "latest.log"
        log_path.write_text(identity_line("TestPlayer"))
        await log_monitor_instance._process_log_changes("test_server", log_path)
        with log_path.open("a") as output:
            output.write("[12:00:01] [Server thread/INFO]: TestPlayer[/127.0.0.1:12345] logged in with entity id 1 at (0, 0, 0)\n")
            output.write(chat_line("TestPlayer", "你好，世界"))
        await log_monitor_instance._process_log_changes("test_server", log_path)
        await log_monitor_instance._process_log_changes("test_server", log_path)
        async with db_session_factory() as session:
            players = list(await session.scalars(select(Player)))
            presence = list(await session.scalars(select(PlayerSession)))
            messages = list(await session.scalars(select(PlayerChatMessage)))
            assert [(p.current_name, p.uuid) for p in players] == [("TestPlayer", make_online_uuid("TestPlayer"))]
            assert len(presence) == 1 and presence[0].left_at is None
            assert presence[0].player_db_id == players[0].player_db_id and presence[0].server_db_id == 1
            assert [(m.message_text, m.server_db_id) for m in messages] == [("你好，世界", 1)]

    async def test_truncated_log_reads_new_content_without_replaying_old_chat(self, log_monitor_instance, tmp_path, db_session_factory):
        log_path = tmp_path / "latest.log"
        log_path.write_text(identity_line("TestPlayer") + chat_line("TestPlayer", "old message"))
        await log_monitor_instance._process_log_changes("test_server", log_path)
        log_path.write_text(chat_line("TestPlayer", "new"))
        await log_monitor_instance._process_log_changes("test_server", log_path)
        await log_monitor_instance._process_log_changes("test_server", log_path)
        async with db_session_factory() as session:
            assert list(await session.scalars(select(PlayerChatMessage.message_text).order_by(PlayerChatMessage.message_id))) == ["old message", "new"]

    async def test_duplicate_watch_and_stop_all_close_real_watchers(self, log_monitor_instance, tmp_path, isolated_runtime):
        for name in ("test_server", "other_server"):
            path = tmp_path / name
            path.mkdir()
            log_path = path / "latest.log"
            log_path.touch()
            await log_monitor_instance._watch_server(name, log_path)
            await log_monitor_instance._watch_server(name, log_path)
        async with asyncio.timeout(5):
            while len(log_monitor_instance._file_pointers) != 2:
                await asyncio.sleep(0)
        subscription = isolated_runtime.event_bus.subscribe()
        try:
            first = tmp_path / "test_server" / "latest.log"
            first.write_text(identity_line("TestPlayer") + chat_line("TestPlayer", "observed"))
            frame = await asyncio.wait_for(subscription.queue.get(), 5)
            assert frame.type == "chat" and frame.message == "observed"
            tasks = list(log_monitor_instance._watch_tasks.values())
            await log_monitor_instance.stop_watching("test_server")
            await log_monitor_instance.stop_watching("test_server")
            assert not log_monitor_instance.is_watching("test_server")
            assert log_monitor_instance.is_watching("other_server")
            await log_monitor_instance.stop_all()
            assert not log_monitor_instance.is_watching("other_server")
            assert all(task.done() for task in tasks)
            assert log_monitor_instance._file_pointers == {}
            assert subscription.queue.empty()
        finally:
            isolated_runtime.event_bus.unsubscribe(subscription)

    async def test_missing_log_can_be_stopped_without_creating_files(self, log_monitor_instance, tmp_path):
        log_path = tmp_path / "missing" / "latest.log"
        await log_monitor_instance._watch_server("test_server", log_path)
        async with asyncio.timeout(5):
            while "test_server" not in log_monitor_instance._file_pointers:
                await asyncio.sleep(0)
        await log_monitor_instance.stop_watching("test_server")
        assert not log_path.exists()
        assert not log_monitor_instance.is_watching("test_server")

    @pytest.mark.asyncio
    async def test_polling_watch_reconciles_unreported_same_mtime_tail(
        self, log_monitor_instance, tmp_path, monkeypatch
    ):
        log_path = tmp_path / "latest.log"
        content = "historical log content\n"

        def replace_log(value):
            staging = tmp_path / "latest.log.tmp"
            staging.write_text(value)
            os.utime(staging, (1700000000, 1700000000))
            staging.replace(log_path)

        await asyncio.to_thread(replace_log, content)
        idle = asyncio.Queue()
        notifications = []
        events = asyncio.Queue()

        async def polling_watch(*paths, **kwargs):
            async for changes in awatch(
                *paths, force_polling=True, poll_delay_ms=50, **kwargs
            ):
                notifications.extend(change for change in changes if change[1] == str(log_path))
                if not changes:
                    idle.put_nowait(None)
                yield changes

        async def capture(event):
            events.put_nowait(event)

        monkeypatch.setattr("app.log_monitor.monitor.awatch", polling_watch)
        monkeypatch.setattr(log_monitor_instance, "_handle_event", capture)
        await log_monitor_instance._watch_server("polling", log_path)
        try:
            await asyncio.wait_for(idle.get(), 5)
            for name in ("FirstPlayer", "SecondPlayer"):
                content += (
                    f"[12:00:00] [Server thread/INFO]: UUID of player {name} "
                    f"is {UUID(make_online_uuid(name))}\n"
                )
                await asyncio.to_thread(replace_log, content)
                event = await asyncio.wait_for(events.get(), 3)
                assert isinstance(event, PlayerUuidDiscoveredEvent)
                assert event.player_name == name
            await asyncio.wait_for(idle.get(), 3)
            assert events.empty()
            assert notifications == []
        finally:
            await log_monitor_instance.stop_watching("polling")

    @pytest.mark.asyncio
    async def test_idle_reconciliation_preserves_delete_recreate_and_truncate(
        self, log_monitor_instance, tmp_path, monkeypatch
    ):
        log_path = tmp_path / "latest.log"
        await asyncio.to_thread(log_path.write_text, "historical" * 100)
        seen = []

        def line(name):
            return (
                f"[12:00:00] [Server thread/INFO]: UUID of player {name} "
                f"is {UUID(make_online_uuid(name))}\n"
            )

        async def event_batches(*args, **kwargs):
            await asyncio.to_thread(log_path.write_text, line("Truncated"))
            yield set()
            yield set()
            await asyncio.to_thread(log_path.unlink)
            yield {(Change.deleted, str(log_path))}
            yield set()
            await asyncio.to_thread(log_path.write_text, line("Recreated"))
            yield {(Change.added, str(log_path))}
            yield set()

        async def capture(event):
            seen.append(event.player_name)

        monkeypatch.setattr("app.log_monitor.monitor.awatch", event_batches)
        monkeypatch.setattr(log_monitor_instance, "_handle_event", capture)
        await log_monitor_instance._watch_loop("rotated", log_path)
        assert seen == ["Truncated", "Recreated"]
