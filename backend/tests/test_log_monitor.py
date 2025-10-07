"""Unit tests for LogMonitor class."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.events.base import PlayerJoinedEvent, PlayerUuidDiscoveredEvent
from app.events.dispatcher import EventDispatcher
from app.log_monitor.monitor import LogMonitor
from app.log_monitor.parser import LogParser


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
    def dispatcher(self):
        """Create event dispatcher."""
        return EventDispatcher()

    @pytest.fixture
    def parser(self, mock_config):
        """Create log parser."""
        return LogParser()

    @pytest.fixture
    def log_monitor(self, dispatcher, parser):
        """Create LogMonitor instance."""
        return LogMonitor(event_dispatcher=dispatcher, log_parser=parser)

    @pytest.mark.asyncio
    async def test_watch_server(self, log_monitor):
        """Test starting to watch a server's log file."""
        server_id = "test_server"
        log_path = Path("/test/server/logs/latest.log")

        # Mock asyncio.create_task to prevent actual watch loop
        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            await log_monitor.watch_server(server_id, log_path)

            # Verify task was created and stored
            assert server_id in log_monitor._watch_tasks
            assert log_monitor._watch_tasks[server_id] == mock_task
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_watch_server_already_watching(self, log_monitor, caplog):
        """Test watching a server that is already being watched."""
        server_id = "test_server"
        log_path = Path("/test/server/logs/latest.log")

        # Add existing task
        existing_task = MagicMock()
        log_monitor._watch_tasks[server_id] = existing_task

        await log_monitor.watch_server(server_id, log_path)

        # Should not create new task, should log warning
        assert log_monitor._watch_tasks[server_id] == existing_task
        assert any("Already watching" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_stop_watching(self, log_monitor):
        """Test stopping watching a server's log file."""
        server_id = "test_server"

        # Create a real task that can be cancelled
        async def dummy_coro():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(dummy_coro())
        log_monitor._watch_tasks[server_id] = task
        log_monitor._file_pointers[server_id] = 100

        await log_monitor.stop_watching(server_id)

        # Verify task was cancelled and removed
        assert server_id not in log_monitor._watch_tasks
        assert server_id not in log_monitor._file_pointers
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_watching_not_watching(self, log_monitor, caplog):
        """Test stopping watching a server that isn't being watched."""
        server_id = "test_server"

        await log_monitor.stop_watching(server_id)

        # Should log warning
        assert any("Not watching" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_stop_all(self, log_monitor):
        """Test stopping all watches."""

        # Create multiple watch tasks
        async def dummy_coro():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        task1 = asyncio.create_task(dummy_coro())
        task2 = asyncio.create_task(dummy_coro())

        log_monitor._watch_tasks["server1"] = task1
        log_monitor._watch_tasks["server2"] = task2

        await log_monitor.stop_all()

        # Verify all tasks were cancelled
        assert len(log_monitor._watch_tasks) == 0
        assert task1.cancelled()
        assert task2.cancelled()
        assert log_monitor._stop_flag is True

    @pytest.mark.asyncio
    async def test_process_log_changes_new_content(self, log_monitor):
        """Test processing new log content."""
        server_id = "test_server"
        log_path = Path("/test/logs/latest.log")

        # Track dispatched events
        dispatched_events = []

        async def track_event(event):
            dispatched_events.append(event)

        log_monitor.event_dispatcher.on_player_joined(track_event)

        # Mock file operations
        with (
            patch("aiofiles.os.path.exists", new_callable=AsyncMock) as mock_exists,
            patch("aiofiles.os.path.getsize", new_callable=AsyncMock) as mock_getsize,
            patch("aiofiles.open") as mock_aioopen,
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 200

            # Create mock file with new content
            log_content = "[12:34:56] [Server thread/INFO]: TestPlayer[/127.0.0.1:12345] logged in with entity id 1 at (0, 0, 0)"

            mock_file = AsyncMock()
            mock_file.read = AsyncMock(return_value=log_content)
            mock_file.seek = AsyncMock()
            mock_file.tell = AsyncMock(return_value=200)

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_file
            mock_ctx.__aexit__.return_value = None
            mock_aioopen.return_value = mock_ctx

            # Set initial pointer
            log_monitor._file_pointers[server_id] = 0

            await log_monitor._process_log_changes(server_id, log_path)

            # Give event handlers time to run
            await asyncio.sleep(0.1)

            # Verify pointer was updated
            assert log_monitor._file_pointers[server_id] == 200

            # Verify event was dispatched
            assert len(dispatched_events) == 1
            assert isinstance(dispatched_events[0], PlayerJoinedEvent)
            assert dispatched_events[0].player_name == "TestPlayer"

    @pytest.mark.asyncio
    async def test_process_log_changes_truncated_file(self, log_monitor):
        """Test processing log when file is truncated (log rotation)."""
        server_id = "test_server"
        log_path = Path("/test/logs/latest.log")

        with (
            patch("aiofiles.os.path.exists", new_callable=AsyncMock) as mock_exists,
            patch("aiofiles.os.path.getsize", new_callable=AsyncMock) as mock_getsize,
            patch("aiofiles.open") as mock_aioopen,
            patch.object(log_monitor, "_dispatch_event"),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 10  # Smaller than current pointer

            mock_file = AsyncMock()
            mock_file.read = AsyncMock(return_value="")
            mock_file.seek = AsyncMock()
            mock_file.tell = AsyncMock(return_value=10)

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_file
            mock_ctx.__aexit__.return_value = None
            mock_aioopen.return_value = mock_ctx

            # Set pointer higher than current file size (indicating truncation)
            log_monitor._file_pointers[server_id] = 1000

            await log_monitor._process_log_changes(server_id, log_path)

            # Verify pointer was reset to beginning
            assert log_monitor._file_pointers[server_id] == 10

            # Verify seek was called with 0 (read from beginning)
            mock_file.seek.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_process_log_changes_no_new_content(self, log_monitor):
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

            # Set pointer equal to file size (no new content)
            log_monitor._file_pointers[server_id] = 100

            await log_monitor._process_log_changes(server_id, log_path)

            # Should not open file
            mock_aioopen.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_event_player_joined(self, log_monitor):
        """Test dispatching PlayerJoinedEvent."""
        dispatched_events = []

        async def track_event(event):
            dispatched_events.append(event)

        log_monitor.event_dispatcher.on_player_joined(track_event)

        event = PlayerJoinedEvent(server_id="test_server", player_name="TestPlayer")

        await log_monitor._dispatch_event(event)

        # Give event handlers time to run
        await asyncio.sleep(0.1)

        assert len(dispatched_events) == 1
        assert dispatched_events[0].player_name == "TestPlayer"

    @pytest.mark.asyncio
    async def test_dispatch_event_player_uuid_discovered(self, log_monitor):
        """Test dispatching PlayerUuidDiscoveredEvent."""
        dispatched_events = []

        async def track_event(event):
            dispatched_events.append(event)

        log_monitor.event_dispatcher.on_player_uuid_discovered(track_event)

        event = PlayerUuidDiscoveredEvent(
            server_id="test_server",
            player_name="TestPlayer",
            uuid="12345678123456781234567812345678",
        )

        await log_monitor._dispatch_event(event)

        # Give event handlers time to run
        await asyncio.sleep(0.1)

        assert len(dispatched_events) == 1
        assert dispatched_events[0].player_name == "TestPlayer"
        assert dispatched_events[0].uuid == "12345678123456781234567812345678"

    @pytest.mark.asyncio
    async def test_dispatch_event_invalid_event(self, log_monitor, caplog):
        """Test dispatching an invalid event."""
        # Pass a non-BaseEvent object
        invalid_event = "not an event"

        await log_monitor._dispatch_event(invalid_event)

        # Should log warning about invalid event
        assert any(
            "Invalid event object" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_watch_loop_file_not_exists_initially(self, log_monitor):
        """Test watch loop when log file doesn't exist initially."""
        server_id = "test_server"
        log_path = Path("/test/logs/latest.log")

        # Mock file not existing
        with (
            patch("aiofiles.os.path.exists", new_callable=AsyncMock) as mock_exists,
            patch("aiofiles.os.path.getsize"),
        ):
            mock_exists.return_value = False

            # Start watch loop in background
            task = asyncio.create_task(log_monitor._watch_loop(server_id, log_path))

            # Give it time to check file
            await asyncio.sleep(0.05)

            # Verify pointer was set to 0
            assert log_monitor._file_pointers[server_id] == 0

            # Stop the watch loop
            log_monitor._stop_flag = True
            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
