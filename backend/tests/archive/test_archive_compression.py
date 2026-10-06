from tests.support.runtime import patch_settings

"""Archive compression tests, including the background-task pipeline."""
import asyncio
import sys
import tempfile
from contextlib import aclosing
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.background_tasks import TaskType, get_task_manager
from app.background_tasks.types import TaskStatus
from app.main import api_app
from app.utils.compression import (
    _sanitize_filename_part,
    create_server_archive_stream,
    generate_archive_filename,
)
from app.utils.exec import exec_command_stream
from tests.support.runtime import patch_runtime_resource


class TestFilenameGeneration:
    def test_sanitize_simple_string(self):
        assert _sanitize_filename_part("test") == "test"

    def test_sanitize_string_with_spaces(self):
        assert _sanitize_filename_part("test server") == "test_server"

    def test_sanitize_string_with_special_chars(self):
        assert _sanitize_filename_part("test:server*name") == "test_server_name"

    def test_sanitize_string_with_slashes(self):
        assert _sanitize_filename_part("test/server\\name") == "test_server_name"

    def test_sanitize_empty_string(self):
        assert _sanitize_filename_part("") == "unknown"

    def test_sanitize_dots_only(self):
        assert _sanitize_filename_part("...") == "unknown"

    def test_generate_filename_server_only(self):
        filename = generate_archive_filename("test_server")
        assert filename.startswith("test_server_")
        assert filename.endswith(".7z")

    def test_generate_filename_with_path(self):
        filename = generate_archive_filename("test_server", "/plugins/config")
        assert "test_server" in filename
        assert "plugins_config" in filename
        assert filename.endswith(".7z")

    def test_generate_filename_with_root_path(self):
        filename = generate_archive_filename("test_server", "/")
        assert "test_server" in filename
        assert filename.endswith(".7z")

    def test_generate_filename_sanitizes_server_name(self):
        filename = generate_archive_filename("test server:2024")
        assert "test_server_2024" in filename
        assert " " not in filename
        assert ":" not in filename


class TestCreateServerArchiveStream:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory(prefix="mc_admin_test_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_instance(self, temp_dir):
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()

        (data_dir / "test.txt").write_text("test content")
        (data_dir / "config.yml").write_text("key: value")

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
        archive_path = temp_dir / "archives"
        archive_path.mkdir()
        return archive_path

    @pytest.mark.asyncio
    @pytest.mark.binary("7z")
    async def test_stream_yields_progress_updates(self, mock_instance, archive_dir):
        with patch_settings() as mock_settings:
            mock_settings.archive_path = archive_dir

            progress_updates = []
            async for progress in create_server_archive_stream(mock_instance):
                progress_updates.append(progress)

            assert len(progress_updates) >= 2

            assert progress_updates[0].progress == 0
            assert "Starting" in progress_updates[0].message

            assert progress_updates[-1].progress == 100
            assert progress_updates[-1].result is not None
            assert "filename" in progress_updates[-1].result

    @pytest.mark.asyncio
    @pytest.mark.binary("7z")
    async def test_stream_creates_archive_file(self, mock_instance, archive_dir):
        with patch_settings() as mock_settings:
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
    @pytest.mark.binary("7z")
    async def test_stream_with_relative_path(self, mock_instance, archive_dir):
        with patch_settings() as mock_settings:
            mock_settings.archive_path = archive_dir

            result = None
            async for progress in create_server_archive_stream(
                mock_instance, "/plugins"
            ):
                if progress.result:
                    result = progress.result

            assert result is not None
            assert "plugins" in result["filename"]
            archive = archive_dir / result["filename"]
            destination = archive_dir / "extracted-plugins"
            process = await asyncio.create_subprocess_exec(
                "7z", "x", str(archive), f"-o{destination}", "-y",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            output, error = await process.communicate()
            assert process.returncode == 0, (output, error)
            assert {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*") if path.is_file()
            } == {"plugins/plugin.jar"}
            assert (destination / "plugins/plugin.jar").read_bytes() == b"\x00\x01\x02\x03" * 100

    @pytest.mark.asyncio
    @pytest.mark.binary("7z")
    async def test_same_instant_compressions_keep_independent_results(self, mock_instance, archive_dir):
        from datetime import UTC, datetime

        results = []
        original = b""
        with (
            patch_settings() as mock_settings,
            patch("app.utils.compression.datetime") as clock,
        ):
            mock_settings.archive_path = archive_dir
            clock.now.return_value = datetime(2026, 9, 7, tzinfo=UTC)
            for content in ("first", "second contents"):
                (mock_instance.get_data_path() / "test.txt").write_text(content)
                async for progress in create_server_archive_stream(mock_instance, "/test.txt"):
                    if progress.result:
                        results.append(progress.result)
                if len(results) == 1:
                    original = (archive_dir / results[0]["filename"]).read_bytes()
        assert results[0]["filename"] != results[1]["filename"]
        assert (archive_dir / results[0]["filename"]).read_bytes() == original
        assert (archive_dir / results[1]["filename"]).stat().st_size == results[1]["size"]
        for index, expected in enumerate((b"first", b"second contents")):
            destination = archive_dir / f"extracted-{index}"
            process = await asyncio.create_subprocess_exec(
                "7z", "x", str(archive_dir / results[index]["filename"]),
                f"-o{destination}", "-y",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            output, error = await process.communicate()
            assert process.returncode == 0, (output, error)
            assert {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*") if path.is_file()
            } == {"test.txt"}
            assert (destination / "test.txt").read_bytes() == expected

    @pytest.mark.asyncio
    async def test_stream_nonexistent_path_raises(self, mock_instance, archive_dir):
        with patch_settings() as mock_settings:
            mock_settings.archive_path = archive_dir

            with pytest.raises(RuntimeError) as exc_info:
                async for _ in create_server_archive_stream(
                    mock_instance, "/nonexistent"
                ):
                    pass

            assert "压缩源路径不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_cleans_up_on_error(self, mock_instance, archive_dir):
        retained = archive_dir / "existing.7z"
        retained.write_bytes(b"existing archive")
        partial = None
        with (
            patch_settings() as mock_settings,
            patch("app.utils.compression.exec_command_stream") as mock_exec,
        ):
            mock_settings.archive_path = archive_dir

            async def failing_generator(*args, **kwargs):
                nonlocal partial
                partial = Path(args[4])
                partial.write_bytes(b"partial archive")
                yield "0%"
                raise RuntimeError("Compression failed")

            mock_exec.side_effect = failing_generator

            with pytest.raises(RuntimeError, match="^Compression failed$"):
                async for _ in create_server_archive_stream(mock_instance):
                    pass
        assert partial is not None and not partial.exists()
        assert retained.read_bytes() == b"existing archive"

    async def test_progress_arrives_before_process_exit(
        self, mock_instance, archive_dir, monkeypatch
    ):
        release = archive_dir / "release"
        archive = archive_dir / "server.7z"

        def controlled_command(*args, **kwargs):
            return exec_command_stream(
                sys.executable, "-u", "-c",
                "import pathlib, sys, time\n"
                "print(' 25%', end=chr(13), flush=True)\n"
                "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'archive')\n"
                "print(' 100%', end=chr(8), flush=True)\n",
                str(release), str(archive), **kwargs,
            )

        monkeypatch.setattr("app.utils.compression.exec_command_stream", controlled_command)
        with patch_settings() as settings:
            settings.archive_path = archive_dir
            async with aclosing(create_server_archive_stream(mock_instance, output_path=archive)) as stream:
                try:
                    async with asyncio.timeout(5):
                        assert (await anext(stream)).progress == 0
                        progress = await anext(stream)
                        assert progress.progress == 25
                        assert progress.message == "Compressing: 25%"
                        assert not archive.exists()
                finally:
                    release.touch()
                async with asyncio.timeout(5):
                    remaining = [progress async for progress in stream]
                assert remaining[-1].progress == 100
                assert remaining[-1].result == {"filename": "server.7z", "size": 7}


class TestArchiveCompressionEndpoint:
    @pytest.fixture
    def client(self):
        return TestClient(api_app)

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory(prefix="mc_admin_test_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def server_setup(self, temp_dir):
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()
        (data_dir / "test.txt").write_text("test content")
        return server_path

    @pytest.fixture
    def mock_server_manager(self, server_setup, temp_dir):
        archive_dir = temp_dir / "archives"
        archive_dir.mkdir()

        mock_submit_result = MagicMock()
        mock_submit_result.task_id = "test-task-id-123"

        with (
            patch_settings() as mock_settings,
            patch_settings() as mock_dep_settings,
            patch_runtime_resource('docker_mc_manager') as mock_manager,
            patch_runtime_resource('task_manager') as mock_task_manager,
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

            async def submit_durable(**kwargs):
                await kwargs["task_generator"].aclose()
                return mock_submit_result

            mock_task_manager.submit_durable = AsyncMock(side_effect=submit_durable)

            yield {
                "archive_dir": archive_dir,
                "server_path": server_setup,
                "task_manager": mock_task_manager,
            }

    def test_endpoint_returns_task_id(self, client, mock_server_manager):
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["task_id"] == "test-task-id-123"

        mock_server_manager["task_manager"].submit_durable.assert_awaited_once()

    def test_endpoint_submits_correct_task_type(self, client, mock_server_manager):
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server"},
        )

        assert response.status_code == 200

        submit = mock_server_manager["task_manager"].submit_durable
        submit.assert_awaited_once()
        call_kwargs = submit.await_args.kwargs
        assert call_kwargs["task_type"] == TaskType.ARCHIVE_CREATE
        assert call_kwargs["server_id"] == "test_server"
        assert call_kwargs["cancellable"] is True
        assert call_kwargs["actor_id"] == 0

    def test_endpoint_nonexistent_server(self, client, temp_dir):
        with (
            patch_settings() as mock_settings,
            patch_settings() as mock_dep_settings,
            patch_runtime_resource('docker_mc_manager') as mock_manager,
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
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server", "path": "/nonexistent"},
        )

        assert response.status_code == 404

    def test_endpoint_unauthorized(self, client, mock_server_manager):
        response = client.post(
            "/archive/compress",
            json={"server_id": "test_server"},
        )

        assert response.status_code in [401, 422]

    def test_endpoint_missing_server_id(self, client, mock_server_manager):
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={},
        )

        assert response.status_code == 422


class TestBackgroundTaskIntegration:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory(prefix="mc_admin_test_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_instance(self, temp_dir):
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()

        for i in range(10):
            (data_dir / f"file_{i}.bin").write_bytes(b"\x00" * 1024 * 100)

        instance = MagicMock()
        instance.get_name.return_value = "test_server"
        instance.get_project_path.return_value = server_path
        instance.get_data_path.return_value = data_dir

        return instance

    @pytest.fixture
    def archive_dir(self, temp_dir):
        archive_path = temp_dir / "archives"
        archive_path.mkdir()
        return archive_path

    @pytest.mark.asyncio
    @pytest.mark.binary("7z")
    async def test_task_manager_runs_compression(self, mock_instance, archive_dir):
        with patch_settings() as mock_settings:
            mock_settings.archive_path = archive_dir

            result = get_task_manager().submit(
                task_type=TaskType.ARCHIVE_CREATE,
                name="test_server",
                task_generator=create_server_archive_stream(mock_instance),
                server_id="test_server",
                cancellable=True,
            )

            task_result = await result.awaitable

            assert task_result.success
            assert task_result.data is not None
            assert "filename" in task_result.data

            task = get_task_manager().get_task(result.task_id)
            assert task is not None
            assert task.status == TaskStatus.COMPLETED
            assert task.progress == 100

            get_task_manager().remove_task(result.task_id)

    @pytest.mark.asyncio
    async def test_task_cancellation(self, mock_instance, archive_dir, monkeypatch):
        from app.utils import exec as exec_module

        release = archive_dir / "release"
        partial: Path | None = None
        children: list[asyncio.subprocess.Process] = []
        spawn = exec_module.spawn_process
        stop = exec_module.stop_process

        async def capture_process(*args, **kwargs):
            child = await spawn(*args, **kwargs)
            children.append(child)
            return child

        def controlled_command(*args, **kwargs):
            nonlocal partial
            partial = Path(args[4])
            return exec_command_stream(
                sys.executable, "-u", "-c",
                "import pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_bytes(b'partial archive')\n"
                "print(' 25%', end=chr(13), flush=True)\n"
                "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.01)\n"
                "pathlib.Path(sys.argv[1]).write_bytes(b'complete archive')\n",
                str(partial), str(release), **kwargs,
            )

        monkeypatch.setattr(exec_module, "spawn_process", capture_process)
        monkeypatch.setattr("app.utils.compression.exec_command_stream", controlled_command)
        with patch_settings() as mock_settings:
            mock_settings.archive_path = archive_dir
            manager = get_task_manager()
            result = manager.submit(
                task_type=TaskType.ARCHIVE_CREATE,
                name="test_server",
                task_generator=create_server_archive_stream(mock_instance),
                server_id="test_server",
                cancellable=True,
            )

            try:
                task = manager.get_task(result.task_id)
                assert task is not None
                async with asyncio.timeout(5):
                    while task.progress != 25:
                        await asyncio.sleep(0.01)
                assert task.status is TaskStatus.RUNNING
                assert len(children) == 1
                child = children[0]
                child_path = Path(f"/proc/{child.pid}")
                assert child.returncode is None and child_path.exists()
                assert partial is not None
                owned_archive = partial
                assert owned_archive.read_bytes() == b"partial archive"
                settled: list[tuple[int | None, bool, bool]] = []

                def observe_completion(_):
                    settled.append((child.returncode, child_path.exists(), owned_archive.exists()))

                result.awaitable.add_done_callback(observe_completion)
                assert await manager.cancel(result.task_id)
                task_result = await asyncio.wait_for(asyncio.shield(result.awaitable), 5)
                assert len(settled) == 1
                assert settled[0][0] is not None
                assert settled[0][1:] == (False, False)
                assert task.status == TaskStatus.CANCELLED
                assert not task_result.success
            finally:
                release.touch()
                try:
                    await manager.cancel(result.task_id)
                    await asyncio.wait_for(asyncio.shield(result.awaitable), 5)
                finally:
                    try:
                        for child in children:
                            try:
                                await asyncio.wait_for(child.wait(), 5)
                            except TimeoutError:
                                await stop(child, grace=1)
                                raise
                    finally:
                        manager.remove_task(result.task_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
