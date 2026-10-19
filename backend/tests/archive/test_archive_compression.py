from tests.support.runtime import patch_settings

"""Archive compression tests, including the background-task pipeline."""
import asyncio
import re
import sys
import tempfile
from contextlib import aclosing
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.background_tasks import TaskType, get_task_manager
from app.background_tasks.types import TaskStatus
from app.main import api_app
from app.operations.journal import OperationJournal
from app.utils.compression import (
    _sanitize_filename_part,
    create_server_archive_stream,
    generate_archive_filename,
)
from app.utils.exec import exec_command_stream


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
        assert re.fullmatch(r"test_server_[0-9]{8}_[0-9]{6}_[0-9]{3}\.7z", filename)

    def test_generate_filename_keeps_browser_local_timestamp(self):
        assert generate_archive_filename("test_server", "20261007_154200_123") == "test_server_20261007_154200_123.7z"

    def test_generate_filename_uses_backend_local_time_for_legacy_clients(self):
        from datetime import datetime, timedelta, timezone

        local = datetime(2026, 10, 7, 15, 42, 0, 123000, tzinfo=timezone(timedelta(hours=8)))
        with patch("app.utils.compression.datetime") as clock:
            clock.now.return_value.astimezone.return_value = local
            assert generate_archive_filename("test_server") == "test_server_20261007_154200_123.7z"

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
            assert progress_updates[0].message == "正在准备压缩"

            assert progress_updates[-1].progress == 100
            assert progress_updates[-1].message == "压缩完成"
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
                mock_instance, "/plugins", client_timestamp="20261007_154200_123",
            ):
                if progress.result:
                    result = progress.result

            assert result is not None
            assert result["filename"] == "test_server_20261007_154200_123.7z"
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
        assert re.fullmatch(r"test_server_[0-9]{8}_[0-9]{6}_[0-9]{3}\.7z", results[0]["filename"])
        assert results[1]["filename"] == results[0]["filename"].removesuffix(".7z") + " (2).7z"
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
                partial = Path(args[args.index("--") - 1])
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
                        assert progress.message == "正在压缩：25%"
                        assert not archive.exists()
                finally:
                    release.touch()
                async with asyncio.timeout(5):
                    remaining = [progress async for progress in stream]
                assert remaining[-1].progress == 100
                assert remaining[-1].result == {"filename": "server.7z", "size": 7}


class TestArchiveCompressionEndpoint:
    @pytest.fixture
    async def archive_application(self, database, isolated_runtime, monkeypatch):
        from httpx2 import ASGITransport, AsyncClient

        from app.servers.models import Server

        runtime = isolated_runtime
        runtime.journal = OperationJournal(database.session_factory)
        monkeypatch.setattr(runtime.settings, "master_token", "compression-test")
        project = runtime.settings.server_path / "survival"
        data = project / "data"
        (data / "plugins" / "empty").mkdir(parents=True)
        (project / "compose.yaml").write_text("services: {}\n")
        (data / "plugins" / "settings.txt").write_text("中文配置与空目录")
        (data / "unselected.txt").write_text("keep outside archive")
        async with database.session_factory() as session:
            session.add(Server(server_id="survival"))
            await session.commit()
        async with AsyncClient(
            transport=ASGITransport(app=api_app), base_url="http://test",
            headers={"Authorization": "Bearer compression-test"},
        ) as client:
            yield client, runtime, data

    @pytest.mark.binary("7z")
    async def test_compression_publishes_verified_content_after_durable_completion(
        self, archive_application, tmp_path, monkeypatch,
    ):
        from app.archive import application
        from app.operations.journal_types import OperationState
        from app.utils.exec import exec_command

        client, runtime, data = archive_application
        entered, release = asyncio.Event(), asyncio.Event()
        compress = application.create_server_archive_stream

        async def held_compression(*args, **kwargs):
            entered.set()
            await release.wait()
            async with aclosing(compress(*args, **kwargs)) as stream:
                async for progress in stream:
                    yield progress

        monkeypatch.setattr(application, "create_server_archive_stream", held_compression)
        try:
            response = await client.post(
                "/archive/compress", json={"server_id": "survival", "path": "plugins"},
            )
            assert response.status_code == 200
            task_id = response.json()["task_id"]
            await asyncio.wait_for(entered.wait(), 5)
            pending = (await client.get(f"/tasks/{task_id}")).json()
            assert pending["status"] == "running" and pending["result"] is None
            assert not list(runtime.settings.archive_path.glob("*.7z"))
            release.set()
            future = runtime.task_manager.get_future(task_id)
            assert future is not None
            terminal = await asyncio.wait_for(future, 15)
            assert terminal.success, terminal.error
            detail = (await client.get(f"/tasks/{task_id}")).json()
            assert detail["status"] == "completed"
            assert detail["task_type"] == TaskType.ARCHIVE_CREATE.value
            published = runtime.settings.archive_path / detail["result"]["filename"]
            extracted = tmp_path / "extracted"
            await exec_command("7z", "x", "-y", f"-o{extracted}", str(published))
            assert (extracted / "plugins" / "settings.txt").read_text() == "中文配置与空目录"
            assert (extracted / "plugins" / "empty").is_dir()
            assert not (extracted / "unselected.txt").exists()
            assert (data / "unselected.txt").read_text() == "keep outside archive"
            record = await OperationJournal(runtime.database.session_factory).get(task_id)
            assert record is not None and record.state is OperationState.SUCCEEDED
            assert record.writers_stopped and record.actor_id == 0
        finally:
            release.set()
            await runtime.task_manager.shutdown()

    @pytest.mark.parametrize(("payload", "expected"), [
        ({"server_id": "missing"}, 404),
        ({"server_id": "survival", "path": "missing"}, 404),
        ({}, 422),
    ])
    async def test_rejected_compression_preserves_files_and_accepts_no_task(
        self, archive_application, payload, expected,
    ):
        client, runtime, data = archive_application
        response = await client.post("/archive/compress", json=payload)
        assert response.status_code == expected
        assert not await OperationJournal(runtime.database.session_factory).list()
        assert not list(runtime.settings.archive_path.iterdir())
        assert (data / "plugins" / "settings.txt").read_text() == "中文配置与空目录"

    async def test_unauthenticated_compression_accepts_no_task(self, archive_application):
        client, runtime, _ = archive_application
        client.headers.pop("Authorization")
        response = await client.post("/archive/compress", json={"server_id": "survival"})
        assert response.status_code == 401
        assert not await OperationJournal(runtime.database.session_factory).list()


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
            partial = Path(args[args.index("--") - 1])
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
