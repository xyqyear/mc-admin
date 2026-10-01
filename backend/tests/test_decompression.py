from tests.support.runtime import patch_settings

"""
Tests for the decompression utility with real command execution.

Tests cover:
- Basic extraction functionality
- Streaming progress updates (extract_archive_stream)
- Minecraft server extraction with TaskProgress (extract_minecraft_server)
- Failure scenarios
- Real-time progress tracking
"""

import asyncio
import errno
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import zipfile
from contextlib import aclosing
from pathlib import Path
from unittest.mock import patch

import aiofiles
import pytest
from aiofiles import os as aioos

from app.background_tasks import TaskStatus, get_task_manager
from app.background_tasks.types import TaskProgress, TaskType
from app.errors import PublicOperationError
from app.utils import async_fs
from app.utils.decompression import (
    extract_archive_stream,
    extract_minecraft_server,
)
from app.utils.exec import exec_command_stream


@pytest.mark.binary("7z")
async def test_decompression_progress_arrives_before_process_exit(temp_dir, mock_settings, monkeypatch):
    archive = temp_dir / "server.zip"
    create_test_archive(archive, {"server.properties": "server-port=25565"})
    release = temp_dir / "release"
    target = temp_dir / "extracted"

    def controlled_command(command, *args, **kwargs):
        return exec_command_stream(
            sys.executable, "-u", "-c",
            "import pathlib, sys, time, zipfile\n"
            "print(' 25%', end=chr(13), flush=True)\n"
            "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
            "with zipfile.ZipFile(sys.argv[2]) as archive: archive.extractall(sys.argv[3])\n"
            "print(' 100%', end=chr(8), flush=True)\n",
            str(release), args[1], args[2].removeprefix("-o"), **kwargs,
        )

    monkeypatch.setattr("app.utils.decompression.exec_command_stream", controlled_command)
    async with aclosing(extract_minecraft_server(str(archive), str(target))) as stream:
        try:
            async with asyncio.timeout(5):
                async for progress in stream:
                    if progress.progress == 27:
                        assert "解压" in progress.message
                        assert not target.exists()
                        break
                else:
                    pytest.fail("No intermediate decompression progress")
        finally:
            release.touch()
        async with asyncio.timeout(5):
            remaining = [progress async for progress in stream]
        assert remaining[-1].progress == 100
        assert remaining[-1].result == {"success": True}
    assert (target / "server.properties").read_text() == "server-port=25565"


@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EACCES, errno.EXDEV])
@pytest.mark.binary("7z")
async def test_failed_publication_preserves_existing_world_and_source(temp_dir, mock_settings, monkeypatch, code):
    archive = temp_dir / "replacement.zip"
    create_test_archive(archive, {"server.properties": "level-name=world", "world/new.dat": "new"})
    target = temp_dir / "data"
    (target / "world").mkdir(parents=True)
    (target / "world" / "old.dat").write_bytes(b"retained world")
    (target / ".settings").write_bytes(b"retained settings")

    async def refuse_exchange(*_):
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(async_fs, "exchange", refuse_exchange)
    with pytest.raises(PublicOperationError, match="原数据保持不变"):
        async for _ in extract_minecraft_server(str(archive), str(target)):
            pass
    assert (target / "world" / "old.dat").read_bytes() == b"retained world"
    assert (target / ".settings").read_bytes() == b"retained settings"
    assert not (target / "world" / "new.dat").exists()
    assert archive.exists()


@pytest.mark.binary("7z")
async def test_publication_replaces_the_complete_tree_including_hidden_files(temp_dir, mock_settings):
    archive = temp_dir / "replacement.zip"
    create_test_archive(archive, {"server.properties": "level-name=world", "world/new.dat": "new", ".settings": "new settings"})
    target = temp_dir / "data"
    (target / "world").mkdir(parents=True)
    (target / "world" / "old.dat").write_bytes(b"old")
    (target / ".old-settings").write_bytes(b"old")
    events = [event async for event in extract_minecraft_server(str(archive), str(target))]
    assert events[-1].result == {"success": True}
    assert (target / "world" / "new.dat").read_text() == "new"
    assert (target / ".settings").read_text() == "new settings"
    assert not (target / "world" / "old.dat").exists()
    assert not (target / ".old-settings").exists()
    assert not archive.exists()


@pytest.mark.binary("7z")
async def test_cleanup_failure_reports_published_data_and_retains_source(temp_dir, mock_settings, monkeypatch):
    archive = temp_dir / "replacement.zip"
    create_test_archive(archive, {"server.properties": "level-name=world", "world/new.dat": "new"})
    target = temp_dir / "data"
    target.mkdir()
    (target / "old.dat").write_bytes(b"old")

    async def refuse_cleanup(*_):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(async_fs, "rmtree", refuse_cleanup)
    with pytest.raises(PublicOperationError, match="服务器文件已替换"):
        async for _ in extract_minecraft_server(str(archive), str(target)):
            pass
    assert (target / "world" / "new.dat").read_text() == "new"
    assert not (target / "old.dat").exists()
    assert archive.exists()


def get_test_user():
    """Get a non-root user for testing permissions."""
    try:
        # Try to find a system user that's not root
        for user_info in pwd.getpwall():
            if (
                user_info.pw_uid != 0  # Not root
                and user_info.pw_uid < 65534  # Not nobody/nogroup
                and user_info.pw_uid != 65534  # Not nobody
                and user_info.pw_shell not in ["/bin/false", "/usr/sbin/nologin"]
                and user_info.pw_name not in ["daemon", "bin", "sys"]
            ):
                return user_info.pw_uid, user_info.pw_gid, user_info.pw_name

        # Fallback to common system users
        for username in ["www-data", "nginx", "apache", "nobody"]:
            try:
                user_info = pwd.getpwnam(username)
                return user_info.pw_uid, user_info.pw_gid, user_info.pw_name
            except KeyError:
                continue

        # If no suitable user found, use a high UID that likely doesn't exist
        return 12345, 12345, "testuser"
    except OSError:
        return 12345, 12345, "testuser"


@pytest.fixture
async def temp_dir():
    """Create a temporary directory for testing archives."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def server_temp_dir():
    """Create a separate temporary directory for server path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def mock_settings(server_temp_dir):
    """Mock settings with separate temporary server path."""
    with patch_settings() as mock_settings:
        mock_settings.server_path = server_temp_dir / "servers"
        # Create server directory
        await aioos.makedirs(mock_settings.server_path, exist_ok=True)
        yield mock_settings


def create_test_archive(archive_path: Path, structure: dict, format_type: str = "zip"):
    """Create a test archive with the given structure."""
    if format_type == "zip":
        with zipfile.ZipFile(archive_path, "w") as zf:
            for file_path, content in structure.items():
                zf.writestr(file_path, content)
    elif format_type == "7z":
        # Create temporary directory structure first
        temp_extract_dir = archive_path.parent / f"{archive_path.stem}_temp"
        temp_extract_dir.mkdir(exist_ok=True)

        for file_path, content in structure.items():
            full_path = temp_extract_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        # Create 7z archive using parent directory as cwd (matching compression.py logic)
        subprocess.run(
            ["7z", "a", str(archive_path), temp_extract_dir.name],
            cwd=str(temp_extract_dir.parent),
            capture_output=True,
            check=True,
        )

        # Clean up temp directory
        shutil.rmtree(temp_extract_dir)


@pytest.mark.binary("7z")
class TestBasicFunctionality:
    """Test basic decompression functionality with real 7z commands."""

    async def test_basic_extraction_success(self, temp_dir, mock_settings):
        """Test successful extraction of a basic Minecraft server archive."""
        # Create test archive
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "server/server.properties": "server-port=25565\ndifficulty=easy\n",
            "server/world/level.dat": "world data here",
            "server/plugins/plugin.jar": "plugin content",
            "server/config.yml": "config content",
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        # Function should complete without raising an exception
        async for _ in extract_minecraft_server(str(archive_path), str(target_path)):
            pass

        # Verify files were actually moved
        assert (target_path / "server.properties").exists()
        assert (target_path / "world" / "level.dat").exists()
        assert (target_path / "plugins" / "plugin.jar").exists()
        assert (target_path / "config.yml").exists()

        # Verify original archive was deleted
        assert not archive_path.exists()

    async def test_different_folder_structures(self, temp_dir, mock_settings):
        """Test extraction with different folder structures."""
        test_cases = [
            # Case 1: server.properties in root
            {
                "server.properties": "server-port=25565\n",
                "world/level.dat": "world data",
            },
            # Case 2: server.properties in nested folder
            {
                "minecraft_server/data/server.properties": "server-port=25565\n",
                "minecraft_server/data/world/level.dat": "world data",
            },
            # Case 3: server.properties in deeply nested structure
            {
                "some/deep/folder/structure/server.properties": "server-port=25565\n",
                "some/deep/folder/structure/plugins/plugin.jar": "plugin",
            },
        ]

        for i, structure in enumerate(test_cases):
            archive_path = temp_dir / f"test_case_{i}.zip"
            create_test_archive(archive_path, structure)

            target_path = temp_dir / f"extracted_{i}"
            await aioos.makedirs(target_path, exist_ok=True)

            # Function should complete without raising an exception
            async for _ in extract_minecraft_server(
                str(archive_path), str(target_path)
            ):
                pass

            # Verify server.properties was moved to target
            assert (target_path / "server.properties").exists()

            # Verify other files at same level as server.properties were also moved
            for file_path in structure:
                if not file_path.endswith("server.properties"):
                    relative_path = Path(file_path).relative_to(
                        Path(file_path).parent.parent if "/" in file_path else Path(".")
                    )
                    if "/" not in str(relative_path):  # File at same level
                        assert (target_path / relative_path.name).exists()

    async def test_7z_format_archive(self, temp_dir, mock_settings):
        """Test extraction with 7z format archive."""
        archive_path = temp_dir / "server.7z"
        server_structure = {
            "mc_server/server.properties": "server-port=25565\n",
            "mc_server/world/level.dat": "world data",
            "mc_server/mods/mod.jar": "mod content",
        }
        create_test_archive(archive_path, server_structure, format_type="7z")

        target_path = temp_dir / "extracted_7z"
        await aioos.makedirs(target_path, exist_ok=True)

        # Function should complete without raising an exception
        async for _ in extract_minecraft_server(str(archive_path), str(target_path)):
            pass

        # Verify files were extracted
        assert (target_path / "server.properties").exists()
        assert (target_path / "world" / "level.dat").exists()
        assert (target_path / "mods" / "mod.jar").exists()


class TestFailureScenarios:
    """Test various failure scenarios with real commands."""

    async def test_archive_not_exists(self, temp_dir, mock_settings):
        """Test failure when archive doesn't exist."""
        archive_path = temp_dir / "nonexistent.zip"
        target_path = temp_dir / "target"

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in extract_minecraft_server(
                str(archive_path), str(target_path)
            ):
                pass

        # Should get error with Chinese error message
        assert "压缩包不存在" in str(exc_info.value)

    @pytest.mark.binary("7z")
    async def test_no_server_properties(self, temp_dir, mock_settings):
        """Test failure when server.properties is not in archive."""
        # Create archive without server.properties
        archive_path = temp_dir / "invalid.zip"
        structure = {"some_file.txt": "content", "folder/another_file.txt": "content"}
        create_test_archive(archive_path, structure)

        target_path = temp_dir / "target"

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in extract_minecraft_server(
                str(archive_path), str(target_path)
            ):
                pass

        # Should get error with Chinese error message
        assert "压缩包中未找到server.properties文件" in str(exc_info.value)

    @pytest.mark.binary("7z")
    async def test_corrupted_archive(self, temp_dir, mock_settings):
        """Test failure with corrupted archive."""
        archive_path = temp_dir / "corrupted.zip"
        # Create a file that looks like a zip but is corrupted
        async with aiofiles.open(archive_path, "w") as f:
            await f.write("This is not a valid zip file")

        target_path = temp_dir / "target"

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in extract_minecraft_server(
                str(archive_path), str(target_path)
            ):
                pass

        # Should get error with Chinese error message about corrupted archive
        assert "压缩包文件损坏或格式不支持" in str(exc_info.value)


class TestNoSevenZip:
    """Test behavior when 7z is not available."""

    async def test_7z_not_installed(self, temp_dir, mock_settings):
        """Test failure when 7z is not installed - mock exec_command for this specific test."""
        archive_path = temp_dir / "test.zip"
        create_test_archive(archive_path, {"server.properties": "content"})
        target_path = temp_dir / "target"

        # Only mock exec_command to simulate 7z not being installed
        with patch("app.utils.decompression.exec_command") as mock_exec:
            mock_exec.side_effect = RuntimeError(
                "Failed to exec command: 7z\n/bin/sh: 7z: command not found"
            )

            with pytest.raises(RuntimeError) as exc_info:
                async for _ in extract_minecraft_server(
                    str(archive_path), str(target_path)
                ):
                    pass

            # Should get error with Chinese error message about 7z not being available
            assert "7z未安装或不可用" in str(exc_info.value)


@pytest.mark.binary("7z")
class TestExtractArchiveStream:
    """Test the low-level extract_archive_stream async generator."""

    async def test_stream_yields_int_percentages(self, temp_dir, mock_settings):
        """Test that extract_archive_stream yields integer percentages."""
        # Create archive with test files
        archive_path = temp_dir / "test.zip"
        server_structure = {
            "server.properties": "server-port=25565\n",
            "world/level.dat": "world data" * 1000,  # Larger file
            "plugins/plugin.jar": "plugin content" * 500,
        }
        create_test_archive(archive_path, server_structure)

        output_dir = temp_dir / "extracted"
        await aioos.makedirs(output_dir, exist_ok=True)

        progress_values = []
        async for percent in extract_archive_stream(str(archive_path), str(output_dir)):
            assert isinstance(percent, int)
            assert 0 <= percent <= 100
            progress_values.append(percent)

        # Should have at least one progress update
        assert len(progress_values) >= 1

    async def test_stream_extracts_files(self, temp_dir, mock_settings):
        """Test that extract_archive_stream actually extracts files."""
        archive_path = temp_dir / "test.zip"
        server_structure = {
            "file.txt": "test content",
            "folder/nested.txt": "nested content",
        }
        create_test_archive(archive_path, server_structure)

        output_dir = temp_dir / "extracted"
        await aioos.makedirs(output_dir, exist_ok=True)

        # Consume the generator
        async for _ in extract_archive_stream(str(archive_path), str(output_dir)):
            pass

        # Verify files were extracted
        assert (output_dir / "file.txt").exists()
        assert (output_dir / "folder" / "nested.txt").exists()

    async def test_stream_7z_archive(self, temp_dir, mock_settings):
        """Test extraction of 7z format archive."""
        archive_path = temp_dir / "test.7z"
        server_structure = {
            "config.yml": "key: value",
            "mods/mod.jar": "mod content",
        }
        create_test_archive(archive_path, server_structure, format_type="7z")

        output_dir = temp_dir / "extracted"
        await aioos.makedirs(output_dir, exist_ok=True)

        async for _ in extract_archive_stream(str(archive_path), str(output_dir)):
            pass

        # 7z extracts into temp dir named after archive
        # Find where files were extracted
        extracted_items = list(output_dir.iterdir())
        assert len(extracted_items) > 0, "No files were extracted"

        # Verify at least some files exist (structure may vary)
        all_files = list(output_dir.rglob("*"))
        file_names = [f.name for f in all_files if f.is_file()]
        assert "config.yml" in file_names, f"config.yml not found in {file_names}"
        assert "mod.jar" in file_names, f"mod.jar not found in {file_names}"


@pytest.mark.binary("7z")
class TestExtractMinecraftServer:
    """Test the high-level extract_minecraft_server async generator."""

    async def test_stream_yields_task_progress(self, temp_dir, mock_settings):
        """Test that stream yields TaskProgress objects."""
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "server/server.properties": "server-port=25565\n",
            "server/world/level.dat": "world data",
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        progress_updates = []
        async for progress in extract_minecraft_server(
            str(archive_path), str(target_path)
        ):
            assert isinstance(progress, TaskProgress)
            assert progress.message is not None
            progress_updates.append(progress)

        # Should have multiple progress updates
        assert len(progress_updates) >= 2

        # First should be 0%
        assert progress_updates[0].progress == 0

        # Last should be 100% with result
        assert progress_updates[-1].progress == 100
        assert progress_updates[-1].result is not None
        assert progress_updates[-1].result.get("success") is True

    async def test_stream_handles_deep_nested_structure(self, temp_dir, mock_settings):
        """Test extraction with deeply nested server.properties."""
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "some/deep/folder/server.properties": "server-port=25565\n",
            "some/deep/folder/world/level.dat": "world data",
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        async for _ in extract_minecraft_server(str(archive_path), str(target_path)):
            pass

        # Verify server.properties is at root of target
        assert (target_path / "server.properties").exists()
        assert (target_path / "world" / "level.dat").exists()

    async def test_stream_progress_mapping(self, temp_dir, mock_settings):
        """Test that progress values are mapped correctly through all steps."""
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "server/server.properties": "server-port=25565\n" * 100,
            "server/world/level.dat": "world data" * 1000,
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        progress_values = []
        messages = []
        async for progress in extract_minecraft_server(
            str(archive_path), str(target_path)
        ):
            if progress.progress is not None:
                progress_values.append(progress.progress)
            messages.append(progress.message)

        # Verify progress is non-decreasing
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i - 1], (
                f"Progress went backwards: {progress_values}"
            )

        # Verify we have expected step messages
        assert any("检查压缩包" in m for m in messages)
        assert any("验证server.properties" in m for m in messages)
        assert any("解压" in m for m in messages)
        assert any("填充完成" in m for m in messages)


class TestBackgroundTaskIntegration:
    """Test decompression with background task manager."""

    @pytest.mark.binary("7z")
    async def test_task_manager_runs_extraction(self, temp_dir, mock_settings):
        """Test that task manager can run extraction task to completion."""
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "server/server.properties": "server-port=25565\n",
            "server/world/level.dat": "world data",
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        result = get_task_manager().submit(
            task_type=TaskType.ARCHIVE_EXTRACT,
            name="test_extract",
            task_generator=extract_minecraft_server(
                str(archive_path), str(target_path)
            ),
            server_id="test_server",
            cancellable=False,
        )

        # Wait for task to complete
        task_result = await result.awaitable

        assert task_result.success
        assert task_result.data is not None
        assert task_result.data.get("success") is True

        # Verify task status
        task = get_task_manager().get_task(result.task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 100

        # Verify files were extracted
        assert (target_path / "server.properties").exists()

        # Clean up
        get_task_manager().remove_task(result.task_id)

    async def test_task_manager_handles_extraction_error(self, temp_dir, mock_settings):
        """Test that task manager handles extraction errors."""
        archive_path = temp_dir / "nonexistent.zip"
        target_path = temp_dir / "target"

        result = get_task_manager().submit(
            task_type=TaskType.ARCHIVE_EXTRACT,
            name="test_extract_fail",
            task_generator=extract_minecraft_server(
                str(archive_path), str(target_path)
            ),
            server_id="test_server",
            cancellable=False,
        )

        # Wait for task to complete (will fail)
        task_result = await result.awaitable

        assert task_result.success is False
        assert task_result.error is not None

        # Verify task status
        task = get_task_manager().get_task(result.task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED

        # Clean up
        get_task_manager().remove_task(result.task_id)

    @pytest.mark.binary("7z")
    async def test_task_tracks_progress_during_extraction(
        self, temp_dir, mock_settings
    ):
        """Test that task progress is updated during extraction."""
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "server.properties": "server-port=25565\n",
            "world/level.dat": "world data" * 1000,
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        result = get_task_manager().submit(
            task_type=TaskType.ARCHIVE_EXTRACT,
            name="test_extract_progress",
            task_generator=extract_minecraft_server(
                str(archive_path), str(target_path)
            ),
            server_id="test_server",
            cancellable=False,
        )

        await result.awaitable

        # Verify final task state
        task = get_task_manager().get_task(result.task_id)
        assert task is not None
        assert task.progress == 100
        assert "填充完成" in task.message

        # Clean up
        get_task_manager().remove_task(result.task_id)
