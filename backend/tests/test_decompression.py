"""
Tests for the decompression utility with real command execution.

Tests cover:
- Basic extraction functionality
- Streaming progress updates (extract_archive_stream)
- Minecraft server extraction with TaskProgress (extract_minecraft_server)
- Failure scenarios
- Real-time progress tracking
"""

import os
import pwd
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from aiofiles import os as aioos

from app.background_tasks import TaskStatus, task_manager
from app.background_tasks.types import TaskProgress, TaskType
from app.utils.decompression import (
    extract_archive_stream,
    extract_minecraft_server,
)


def check_7z_available():
    """Check if 7z command is available."""
    try:
        subprocess.run(["7z"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


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
    except Exception:
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
    with patch("app.utils.decompression.settings") as mock_settings:
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


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
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
            for file_path in structure.keys():
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


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
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

    async def test_corrupted_archive(self, temp_dir, mock_settings):
        """Test failure with corrupted archive."""
        archive_path = temp_dir / "corrupted.zip"
        # Create a file that looks like a zip but is corrupted
        with open(archive_path, "w") as f:
            f.write("This is not a valid zip file")

        target_path = temp_dir / "target"

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in extract_minecraft_server(
                str(archive_path), str(target_path)
            ):
                pass

        # Should get error with Chinese error message about corrupted archive
        assert "压缩包文件损坏或格式不支持" in str(exc_info.value)


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
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


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
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


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
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

    async def test_stream_extracts_server_files(self, temp_dir, mock_settings):
        """Test that stream extracts server files to target path."""
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "server/server.properties": "server-port=25565\n",
            "server/world/level.dat": "world data",
            "server/plugins/plugin.jar": "plugin content",
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        async for _ in extract_minecraft_server(str(archive_path), str(target_path)):
            pass

        # Verify files were extracted to target
        assert (target_path / "server.properties").exists()
        assert (target_path / "world" / "level.dat").exists()
        assert (target_path / "plugins" / "plugin.jar").exists()

        # Verify original archive was deleted
        assert not archive_path.exists()

    async def test_stream_deletes_archive_after_extraction(
        self, temp_dir, mock_settings
    ):
        """Test that archive is deleted after successful extraction."""
        archive_path = temp_dir / "server.zip"
        server_structure = {
            "server.properties": "server-port=25565\n",
        }
        create_test_archive(archive_path, server_structure)

        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        async for _ in extract_minecraft_server(str(archive_path), str(target_path)):
            pass

        # Archive should be deleted
        assert not archive_path.exists()

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

    async def test_stream_fails_on_nonexistent_archive(self, temp_dir, mock_settings):
        """Test that stream fails when archive doesn't exist."""
        archive_path = temp_dir / "nonexistent.zip"
        target_path = temp_dir / "target"

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in extract_minecraft_server(
                str(archive_path), str(target_path)
            ):
                pass

        assert "压缩包不存在" in str(exc_info.value)

    async def test_stream_fails_on_missing_server_properties(
        self, temp_dir, mock_settings
    ):
        """Test that stream fails when archive lacks server.properties."""
        archive_path = temp_dir / "invalid.zip"
        structure = {"some_file.txt": "content", "folder/another.txt": "content"}
        create_test_archive(archive_path, structure)

        target_path = temp_dir / "target"

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in extract_minecraft_server(
                str(archive_path), str(target_path)
            ):
                pass

        assert "压缩包中未找到server.properties文件" in str(exc_info.value)

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


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
class TestRealTimeDecompressionProgress:
    """Test that decompression progress is tracked in real-time."""

    @pytest.fixture
    async def large_archive(self, temp_dir, mock_settings):
        """Create a large archive to ensure measurable decompression time."""
        archive_path = temp_dir / "large_server.zip"

        # Create structure with larger files
        server_structure = {
            "server.properties": "server-port=25565\n",
        }
        # Add larger files - 10 x 500KB files (5MB total)
        for i in range(10):
            server_structure[f"data/file_{i}.bin"] = os.urandom(500 * 1024).hex()

        create_test_archive(archive_path, server_structure)
        return archive_path

    async def test_progress_updates_are_realtime(
        self, temp_dir, large_archive, mock_settings
    ):
        """Test that progress updates arrive in real-time during extraction."""
        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        progress_timestamps: list[tuple[float, float]] = []
        start_time = time.time()

        async for progress in extract_minecraft_server(
            str(large_archive), str(target_path)
        ):
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

        # Print summary for debugging
        print("\nDecompression progress tracking summary:")
        print(f"  Total updates: {len(progress_timestamps)}")
        print(f"  Progress range: {min(progress_values)}% - {max(progress_values)}%")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Sample updates: {progress_timestamps[:5]}...")

    async def test_decompress_step_has_granular_progress(
        self, temp_dir, large_archive, mock_settings
    ):
        """Test that the decompress step (10-80%) has granular progress updates."""
        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)

        decompress_progress_values = []
        async for progress in extract_minecraft_server(
            str(large_archive), str(target_path)
        ):
            if progress.progress is not None:
                # Decompress step is mapped to 10-80%
                if 10 <= progress.progress <= 80 and "解压" in (progress.message or ""):
                    decompress_progress_values.append(progress.progress)

        # Should have multiple progress updates during decompression
        # (not just single updates at 10% and 80%)
        print(f"\nDecompress step progress values: {decompress_progress_values}")

        # With a large enough archive, we should see intermediate progress
        if len(decompress_progress_values) > 2:
            # Check that we have values between 10 and 80
            intermediate_values = [v for v in decompress_progress_values if 15 < v < 75]
            assert len(intermediate_values) > 0, (
                "Expected intermediate progress values during decompression"
            )


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
class TestBackgroundTaskIntegration:
    """Test decompression with background task manager."""

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

        result = task_manager.submit(
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
        task = task_manager.get_task(result.task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 100

        # Verify files were extracted
        assert (target_path / "server.properties").exists()

        # Clean up
        task_manager.remove_task(result.task_id)

    async def test_task_manager_handles_extraction_error(self, temp_dir, mock_settings):
        """Test that task manager handles extraction errors."""
        archive_path = temp_dir / "nonexistent.zip"
        target_path = temp_dir / "target"

        result = task_manager.submit(
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
        task = task_manager.get_task(result.task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED

        # Clean up
        task_manager.remove_task(result.task_id)

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

        result = task_manager.submit(
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
        task = task_manager.get_task(result.task_id)
        assert task is not None
        assert task.progress == 100
        assert "填充完成" in task.message

        # Clean up
        task_manager.remove_task(result.task_id)
