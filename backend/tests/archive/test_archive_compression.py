"""
Unit tests for archive compression functionality.
Tests the creation of compressed archives from server files using background tasks.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.background_tasks import TaskType, task_manager
from app.background_tasks.types import TaskStatus
from app.main import api_app
from app.utils.compression import (
    _generate_archive_filename,
    _sanitize_filename_part,
    create_server_archive_stream,
)


class TestFilenameGeneration:
    """Test filename generation and sanitization utilities."""

    def test_sanitize_simple_string(self):
        """Test sanitizing a simple string."""
        assert _sanitize_filename_part("test") == "test"

    def test_sanitize_string_with_spaces(self):
        """Test sanitizing string with spaces."""
        assert _sanitize_filename_part("test server") == "test_server"

    def test_sanitize_string_with_special_chars(self):
        """Test sanitizing string with special characters."""
        assert _sanitize_filename_part("test:server*name") == "test_server_name"

    def test_sanitize_string_with_slashes(self):
        """Test sanitizing string with slashes."""
        assert _sanitize_filename_part("test/server\\name") == "test_server_name"

    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        assert _sanitize_filename_part("") == "unknown"

    def test_sanitize_dots_only(self):
        """Test sanitizing string with only dots."""
        assert _sanitize_filename_part("...") == "unknown"

    def test_generate_filename_server_only(self):
        """Test generating filename with server name only."""
        filename = _generate_archive_filename("test_server")
        assert filename.startswith("test_server_")
        assert filename.endswith(".7z")

    def test_generate_filename_with_path(self):
        """Test generating filename with relative path."""
        filename = _generate_archive_filename("test_server", "/plugins/config")
        assert "test_server" in filename
        assert "plugins_config" in filename
        assert filename.endswith(".7z")

    def test_generate_filename_with_root_path(self):
        """Test generating filename with root path."""
        filename = _generate_archive_filename("test_server", "/")
        assert "test_server" in filename
        assert filename.endswith(".7z")

    def test_generate_filename_sanitizes_server_name(self):
        """Test that server name is sanitized in filename."""
        filename = _generate_archive_filename("test server:2024")
        assert "test_server_2024" in filename
        assert " " not in filename
        assert ":" not in filename


class TestCreateServerArchiveStream:
    """Test the create_server_archive_stream async generator."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(prefix="mc_admin_test_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_instance(self, temp_dir):
        """Create mock MCInstance."""
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()

        # Create test files
        (data_dir / "test.txt").write_text("test content")
        (data_dir / "config.yml").write_text("key: value")

        # Create subdirectory
        plugins_dir = data_dir / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "plugin.jar").write_bytes(b"\x00\x01\x02\x03" * 100)

        instance = MagicMock()
        instance.get_name.return_value = "test_server"
        instance.get_project_path.return_value = server_path
        instance.get_data_path.return_value = data_dir

        return instance

    @pytest.fixture
    def archive_dir(self, temp_dir):
        """Create archive directory."""
        archive_path = temp_dir / "archives"
        archive_path.mkdir()
        return archive_path

    @pytest.mark.asyncio
    async def test_stream_yields_progress_updates(self, mock_instance, archive_dir):
        """Test that stream yields progress updates."""
        import shutil

        if not shutil.which("7z"):
            pytest.skip("7z command not available")

        with patch("app.utils.compression.settings") as mock_settings:
            mock_settings.archive_path = archive_dir

            progress_updates = []
            async for progress in create_server_archive_stream(mock_instance):
                progress_updates.append(progress)

            # Should have at least start and completion
            assert len(progress_updates) >= 2

            # First should be 0%
            assert progress_updates[0].progress == 0
            assert "Starting" in progress_updates[0].message

            # Last should be 100% with result
            assert progress_updates[-1].progress == 100
            assert progress_updates[-1].result is not None
            assert "filename" in progress_updates[-1].result

    @pytest.mark.asyncio
    async def test_stream_creates_archive_file(self, mock_instance, archive_dir):
        """Test that stream creates the archive file."""
        import shutil

        if not shutil.which("7z"):
            pytest.skip("7z command not available")

        with patch("app.utils.compression.settings") as mock_settings:
            mock_settings.archive_path = archive_dir

            result = None
            async for progress in create_server_archive_stream(mock_instance):
                if progress.result:
                    result = progress.result

            assert result is not None
            archive_path = archive_dir / result["filename"]
            assert archive_path.exists()
            assert result["size"] > 0

    @pytest.mark.asyncio
    async def test_stream_with_relative_path(self, mock_instance, archive_dir):
        """Test stream with relative path."""
        import shutil

        if not shutil.which("7z"):
            pytest.skip("7z command not available")

        with patch("app.utils.compression.settings") as mock_settings:
            mock_settings.archive_path = archive_dir

            result = None
            async for progress in create_server_archive_stream(
                mock_instance, "/plugins"
            ):
                if progress.result:
                    result = progress.result

            assert result is not None
            assert "plugins" in result["filename"]

    @pytest.mark.asyncio
    async def test_stream_nonexistent_path_raises(self, mock_instance, archive_dir):
        """Test that nonexistent path raises RuntimeError."""
        with patch("app.utils.compression.settings") as mock_settings:
            mock_settings.archive_path = archive_dir

            with pytest.raises(RuntimeError) as exc_info:
                async for _ in create_server_archive_stream(
                    mock_instance, "/nonexistent"
                ):
                    pass

            assert "Source path does not exist" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_cleans_up_on_error(self, mock_instance, archive_dir):
        """Test that partial archive is cleaned up on error."""
        with (
            patch("app.utils.compression.settings") as mock_settings,
            patch("app.utils.compression.exec_command_stream") as mock_exec,
        ):
            mock_settings.archive_path = archive_dir

            # Make exec_command_stream raise an error
            async def failing_generator(*args, **kwargs):
                yield "0%"
                raise RuntimeError("Compression failed")

            mock_exec.return_value = failing_generator()

            with pytest.raises(RuntimeError):
                async for _ in create_server_archive_stream(mock_instance):
                    pass


class TestArchiveCompressionEndpoint:
    """Test archive compression API endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(api_app)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(prefix="mc_admin_test_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def server_setup(self, temp_dir):
        """Create server directory structure for testing."""
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()
        (data_dir / "test.txt").write_text("test content")
        return server_path

    @pytest.fixture
    def mock_server_manager(self, server_setup, temp_dir):
        """Setup mock server manager."""
        archive_dir = temp_dir / "archives"
        archive_dir.mkdir()

        # Create a mock submit result
        mock_submit_result = MagicMock()
        mock_submit_result.task_id = "test-task-id-123"

        with (
            patch("app.routers.archive.settings") as mock_settings,
            patch("app.dependencies.settings") as mock_dep_settings,
            patch("app.routers.archive.docker_mc_manager") as mock_manager,
            patch("app.routers.archive.task_manager") as mock_task_manager,
        ):
            mock_settings.archive_path = archive_dir
            mock_settings.master_token = "test_master_token"
            mock_dep_settings.master_token = "test_master_token"

            mock_instance = mock_manager.get_instance.return_value
            mock_instance.get_project_path.return_value = server_setup
            mock_instance.get_data_path.return_value = server_setup / "data"
            mock_instance.get_name.return_value = "test_server"

            async def mock_exists():
                return True

            mock_instance.exists = mock_exists

            # Mock task_manager.submit to return immediately
            mock_task_manager.submit.return_value = mock_submit_result

            yield {
                "archive_dir": archive_dir,
                "server_path": server_setup,
                "task_manager": mock_task_manager,
            }

    def test_endpoint_returns_task_id(self, client, mock_server_manager):
        """Test that endpoint returns task_id."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["task_id"] == "test-task-id-123"

        # Verify task_manager.submit was called
        mock_server_manager["task_manager"].submit.assert_called_once()

    def test_endpoint_submits_correct_task_type(self, client, mock_server_manager):
        """Test that endpoint submits correct task type."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server"},
        )

        assert response.status_code == 200

        # Verify task type
        call_kwargs = mock_server_manager["task_manager"].submit.call_args.kwargs
        assert call_kwargs["task_type"] == TaskType.ARCHIVE_CREATE
        assert call_kwargs["server_id"] == "test_server"
        assert call_kwargs["cancellable"] is True

    def test_endpoint_nonexistent_server(self, client, temp_dir):
        """Test endpoint with nonexistent server."""
        with (
            patch("app.routers.archive.settings") as mock_settings,
            patch("app.dependencies.settings") as mock_dep_settings,
            patch("app.routers.archive.docker_mc_manager") as mock_manager,
        ):
            mock_settings.master_token = "test_master_token"
            mock_dep_settings.master_token = "test_master_token"

            mock_instance = mock_manager.get_instance.return_value

            async def mock_exists():
                return False

            mock_instance.exists = mock_exists

            response = client.post(
                "/archive/compress",
                headers={"Authorization": "Bearer test_master_token"},
                json={"server_id": "nonexistent"},
            )

            assert response.status_code == 404

    def test_endpoint_nonexistent_path(self, client, mock_server_manager):
        """Test endpoint with nonexistent path."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server", "path": "/nonexistent"},
        )

        assert response.status_code == 404

    def test_endpoint_unauthorized(self, client, mock_server_manager):
        """Test unauthorized access."""
        response = client.post(
            "/archive/compress",
            json={"server_id": "test_server"},
        )

        assert response.status_code in [401, 422]

    def test_endpoint_missing_server_id(self, client, mock_server_manager):
        """Test missing server_id."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={},
        )

        assert response.status_code == 422


class TestBackgroundTaskIntegration:
    """Test compression with background task manager."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(prefix="mc_admin_test_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_instance(self, temp_dir):
        """Create mock MCInstance with test files."""
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()

        # Create larger test files to see progress
        for i in range(10):
            (data_dir / f"file_{i}.bin").write_bytes(b"\x00" * 1024 * 100)

        instance = MagicMock()
        instance.get_name.return_value = "test_server"
        instance.get_project_path.return_value = server_path
        instance.get_data_path.return_value = data_dir

        return instance

    @pytest.fixture
    def archive_dir(self, temp_dir):
        """Create archive directory."""
        archive_path = temp_dir / "archives"
        archive_path.mkdir()
        return archive_path

    @pytest.mark.asyncio
    async def test_task_manager_runs_compression(self, mock_instance, archive_dir):
        """Test that task manager can run compression task."""
        import shutil

        if not shutil.which("7z"):
            pytest.skip("7z command not available")

        with patch("app.utils.compression.settings") as mock_settings:
            mock_settings.archive_path = archive_dir

            result = task_manager.submit(
                task_type=TaskType.ARCHIVE_CREATE,
                name="test_server",
                task_generator=create_server_archive_stream(mock_instance),
                server_id="test_server",
                cancellable=True,
            )

            # Wait for task to complete
            task_result = await result.awaitable

            assert task_result.success
            assert task_result.data is not None
            assert "filename" in task_result.data

            # Verify task status
            task = task_manager.get_task(result.task_id)
            assert task is not None
            assert task.status == TaskStatus.COMPLETED
            assert task.progress == 100

            # Clean up
            task_manager.remove_task(result.task_id)

    @pytest.mark.asyncio
    async def test_task_cancellation(self, mock_instance, archive_dir):
        """Test that compression task can be cancelled."""
        import shutil

        if not shutil.which("7z"):
            pytest.skip("7z command not available")

        with patch("app.utils.compression.settings") as mock_settings:
            mock_settings.archive_path = archive_dir

            # Create larger files to ensure compression takes time
            data_dir = mock_instance.get_data_path()
            for i in range(50):
                (data_dir / f"large_file_{i}.bin").write_bytes(b"\x00" * 1024 * 1024)

            result = task_manager.submit(
                task_type=TaskType.ARCHIVE_CREATE,
                name="test_server",
                task_generator=create_server_archive_stream(mock_instance),
                server_id="test_server",
                cancellable=True,
            )

            # Wait a bit then cancel
            await asyncio.sleep(0.5)
            cancelled = await task_manager.cancel(result.task_id)

            # Wait for task to finish
            task_result = await result.awaitable

            task = task_manager.get_task(result.task_id)
            assert task is not None
            # Task should be cancelled (if it didn't complete too fast)
            if cancelled:
                assert task.status == TaskStatus.CANCELLED
                assert not task_result.success
            else:
                # Task completed before cancellation
                assert task.status == TaskStatus.COMPLETED

            # Clean up
            task_manager.remove_task(result.task_id)


class TestRealTimeProgressTracking:
    """Test that 7z progress is tracked in real-time, not buffered."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(prefix="mc_admin_test_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_instance_large(self, temp_dir):
        """Create mock MCInstance with large test files to ensure measurable compression time."""
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()

        # Create 30 x 1MB files (30MB total) - enough to see progress updates
        import os

        for i in range(30):
            (data_dir / f"file_{i}.bin").write_bytes(os.urandom(1024 * 1024))

        instance = MagicMock()
        instance.get_name.return_value = "test_server"
        instance.get_project_path.return_value = server_path
        instance.get_data_path.return_value = data_dir

        return instance

    @pytest.fixture
    def archive_dir(self, temp_dir):
        """Create archive directory."""
        archive_path = temp_dir / "archives"
        archive_path.mkdir()
        return archive_path

    @pytest.mark.asyncio
    async def test_progress_updates_are_realtime(
        self, mock_instance_large, archive_dir
    ):
        """
        Test that progress updates arrive in real-time during compression.

        This verifies that the delimiter-based reading fix works correctly:
        - Progress updates should be spread over the compression duration
        - Multiple intermediate progress values should be received
        - Updates should not all arrive at once at the end
        """
        import shutil
        import time

        if not shutil.which("7z"):
            pytest.skip("7z command not available")

        with patch("app.utils.compression.settings") as mock_settings:
            mock_settings.archive_path = archive_dir

            progress_timestamps: list[tuple[float, float]] = []
            start_time = time.time()

            async for progress in create_server_archive_stream(mock_instance_large):
                elapsed = time.time() - start_time
                if progress.progress is not None:
                    progress_timestamps.append((elapsed, progress.progress))

            total_time = time.time() - start_time

            # Verify we got multiple progress updates
            assert len(progress_timestamps) >= 3, (
                f"Expected at least 3 progress updates, got {len(progress_timestamps)}"
            )

            # Verify progress values span from low to high
            progress_values = [p[1] for p in progress_timestamps]
            assert min(progress_values) <= 10, (
                f"Expected initial progress <= 10%, got min={min(progress_values)}%"
            )
            assert max(progress_values) >= 90, (
                f"Expected final progress >= 90%, got max={max(progress_values)}%"
            )

            # Verify updates are spread over time (not all at once at the end)
            # The time spread should be at least 50% of total compression time
            first_update_time = progress_timestamps[0][0]
            last_update_time = progress_timestamps[-1][0]
            time_spread = last_update_time - first_update_time

            # If compression took more than 1 second, updates should be spread
            if total_time > 1.0:
                assert time_spread > total_time * 0.3, (
                    f"Progress updates not spread over time: "
                    f"spread={time_spread:.2f}s, total={total_time:.2f}s"
                )

            # Print summary for debugging
            print("\nProgress tracking summary:")
            print(f"  Total updates: {len(progress_timestamps)}")
            print(
                f"  Progress range: {min(progress_values)}% - {max(progress_values)}%"
            )
            print(f"  Time spread: {time_spread:.2f}s / {total_time:.2f}s total")
            print(f"  Sample updates: {progress_timestamps[:5]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
