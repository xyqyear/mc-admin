"""Unit tests for LogMonitor class."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.log_monitor.events import PlayerJoinedEvent, PlayerUuidDiscoveredEvent
from app.log_monitor.monitor import LogMonitor
from tests.players.helpers import make_online_uuid


@pytest.fixture
def mock_config():
    """Mock dynamic config for LogParser."""
    from app.dynamic_config.configs.log_parser import LogParserConfig

    mock_log_parser_config = LogParserConfig.model_validate({})
    mock_config_obj = MagicMock()
    mock_config_obj.log_parser = mock_log_parser_config

    with patch("app.log_monitor.parser.config", mock_config_obj):
        yield mock_config_obj


class TestLogMonitor:
    """Test LogMonitor class."""

    @pytest.fixture
    def log_monitor_instance(self, mock_config):
        """Create LogMonitor instance."""
        return LogMonitor()

    @pytest.mark.asyncio
    async def test_watch_server(self, log_monitor_instance):
        """Test starting to watch a server's log file."""
        server_id = "test_server"
        log_path = Path("/test/server/logs/latest.log")

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            await log_monitor_instance._watch_server(server_id, log_path)

            assert server_id in log_monitor_instance._watch_tasks
            assert log_monitor_instance._watch_tasks[server_id] == mock_task
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_watch_server_already_watching(self, log_monitor_instance, caplog):
        """Test watching a server that is already being watched."""
        server_id = "test_server"
        log_path = Path("/test/server/logs/latest.log")

        existing_task = MagicMock()
        log_monitor_instance._watch_tasks[server_id] = existing_task

        await log_monitor_instance._watch_server(server_id, log_path)

        assert log_monitor_instance._watch_tasks[server_id] == existing_task
        assert any("Already watching" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_stop_watching(self, log_monitor_instance):
        """Test stopping watching a server's log file."""
        server_id = "test_server"

        async def dummy_coro():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(dummy_coro())
        log_monitor_instance._watch_tasks[server_id] = task
        log_monitor_instance._file_pointers[server_id] = 100

        await log_monitor_instance.stop_watching(server_id)

        assert server_id not in log_monitor_instance._watch_tasks
        assert server_id not in log_monitor_instance._file_pointers
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_watching_not_watching(self, log_monitor_instance, caplog):
        """Test stopping watching a server that isn't being watched."""
        server_id = "test_server"

        await log_monitor_instance.stop_watching(server_id)

        assert any("Not watching" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_stop_all(self, log_monitor_instance):
        """Test stopping all watches."""

        async def dummy_coro():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        task1 = asyncio.create_task(dummy_coro())
        task2 = asyncio.create_task(dummy_coro())

        log_monitor_instance._watch_tasks["server1"] = task1
        log_monitor_instance._watch_tasks["server2"] = task2

        await log_monitor_instance.stop_all()

        assert len(log_monitor_instance._watch_tasks) == 0
        assert task1.cancelled()
        assert task2.cancelled()
        assert log_monitor_instance._stop_flag is True

    @pytest.mark.asyncio
    async def test_process_log_changes_new_content(self, log_monitor_instance):
        """Test processing new log content."""
        server_id = "test_server"
        log_path = Path("/test/logs/latest.log")

        with (
            patch("aiofiles.os.path.exists", new_callable=AsyncMock) as mock_exists,
            patch("aiofiles.os.path.getsize", new_callable=AsyncMock) as mock_getsize,
            patch("aiofiles.open") as mock_aioopen,
            patch(
                "app.log_monitor.monitor.process_player_join", new_callable=AsyncMock
            ) as mock_join,
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 200

            log_content = "[12:34:56] [Server thread/INFO]: TestPlayer[/127.0.0.1:12345] logged in with entity id 1 at (0, 0, 0)"

            mock_file = AsyncMock()
            mock_file.read = AsyncMock(return_value=log_content)
            mock_file.seek = AsyncMock()
            mock_file.tell = AsyncMock(return_value=200)

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_file
            mock_ctx.__aexit__.return_value = None
            mock_aioopen.return_value = mock_ctx

            log_monitor_instance._file_pointers[server_id] = 0

            await log_monitor_instance._process_log_changes(server_id, log_path)

            assert log_monitor_instance._file_pointers[server_id] == 200
            mock_join.assert_called_once()
            assert mock_join.call_args[0][1] == "TestPlayer"

    @pytest.mark.asyncio
    async def test_process_log_changes_truncated_file(self, log_monitor_instance):
        """Test processing log when file is truncated (log rotation)."""
        server_id = "test_server"
        log_path = Path("/test/logs/latest.log")

        with (
            patch("aiofiles.os.path.exists", new_callable=AsyncMock) as mock_exists,
            patch("aiofiles.os.path.getsize", new_callable=AsyncMock) as mock_getsize,
            patch("aiofiles.open") as mock_aioopen,
            patch.object(log_monitor_instance, "_handle_event", new_callable=AsyncMock),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 10

            mock_file = AsyncMock()
            mock_file.read = AsyncMock(return_value="")
            mock_file.seek = AsyncMock()
            mock_file.tell = AsyncMock(return_value=10)

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_file
            mock_ctx.__aexit__.return_value = None
            mock_aioopen.return_value = mock_ctx

            log_monitor_instance._file_pointers[server_id] = 1000

            await log_monitor_instance._process_log_changes(server_id, log_path)

            assert log_monitor_instance._file_pointers[server_id] == 10
            mock_file.seek.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_process_log_changes_no_new_content(self, log_monitor_instance):
        """Test processing log when there's no new content."""
        server_id = "test_server"
        log_path = Path("/test/logs/latest.log")

        with (
            patch("aiofiles.os.path.exists", new_callable=AsyncMock) as mock_exists,
            patch("aiofiles.os.path.getsize", new_callable=AsyncMock) as mock_getsize,
            patch("aiofiles.open") as mock_aioopen,
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 100

            log_monitor_instance._file_pointers[server_id] = 100

            await log_monitor_instance._process_log_changes(server_id, log_path)

            mock_aioopen.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_event_player_joined(self, log_monitor_instance):
        """Test handling PlayerJoinedEvent calls process_player_join."""
        event = PlayerJoinedEvent(server_id="test_server", player_name="TestPlayer")

        with patch(
            "app.log_monitor.monitor.process_player_join", new_callable=AsyncMock
        ) as mock_join:
            await log_monitor_instance._handle_event(event)
            mock_join.assert_called_once_with(
                event.server_id, event.player_name, event.timestamp
            )

    @pytest.mark.asyncio
    async def test_handle_event_uuid_discovered(self, log_monitor_instance):
        """Test handling PlayerUuidDiscoveredEvent calls upsert_player."""
        uuid = make_online_uuid("TestPlayer")
        event = PlayerUuidDiscoveredEvent(
            server_id="test_server",
            player_name="TestPlayer",
            uuid=uuid,
        )

        with patch("app.log_monitor.monitor.get_async_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_session
            mock_get_session.return_value = mock_ctx

            with patch(
                "app.log_monitor.monitor.upsert_player", new_callable=AsyncMock
            ) as mock_upsert:
                await log_monitor_instance._handle_event(event)
                mock_upsert.assert_called_once_with(
                    mock_session, uuid, "TestPlayer"
                )

    @pytest.mark.asyncio
    async def test_watch_loop_file_not_exists_initially(self, log_monitor_instance):
        """Test watch loop when log file doesn't exist initially."""
        server_id = "test_server"
        log_path = Path("/test/logs/latest.log")

        with (
            patch("aiofiles.os.path.exists", new_callable=AsyncMock) as mock_exists,
            patch("aiofiles.os.path.getsize"),
        ):
            mock_exists.return_value = False

            task = asyncio.create_task(
                log_monitor_instance._watch_loop(server_id, log_path)
            )

            await asyncio.sleep(0.05)

            assert log_monitor_instance._file_pointers[server_id] == 0

            log_monitor_instance._stop_flag = True
            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
