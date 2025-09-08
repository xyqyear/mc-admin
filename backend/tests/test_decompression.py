"""
Tests for the decompression utility with real command execution.
"""

import os
import pwd
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from aiofiles import os as aioos
from fastapi import HTTPException

from app.utils.decompression import (
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

        # Create 7z archive
        subprocess.run(
            ["7z", "a", str(archive_path), f"{temp_extract_dir}/*"],
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
        await extract_minecraft_server(str(archive_path), str(target_path))

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
            await extract_minecraft_server(str(archive_path), str(target_path))

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
        await extract_minecraft_server(str(archive_path), str(target_path))

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

        with pytest.raises(HTTPException) as exc_info:
            await extract_minecraft_server(str(archive_path), str(target_path))

        # Should get 404 with Chinese error message
        assert exc_info.value.status_code == 404
        assert "压缩包不存在" in exc_info.value.detail

    async def test_no_server_properties(self, temp_dir, mock_settings):
        """Test failure when server.properties is not in archive."""
        # Create archive without server.properties
        archive_path = temp_dir / "invalid.zip"
        structure = {"some_file.txt": "content", "folder/another_file.txt": "content"}
        create_test_archive(archive_path, structure)

        target_path = temp_dir / "target"

        with pytest.raises(HTTPException) as exc_info:
            await extract_minecraft_server(str(archive_path), str(target_path))

        # Should get 400 with Chinese error message
        assert exc_info.value.status_code == 400
        assert "压缩包中未找到server.properties文件" in exc_info.value.detail

    async def test_corrupted_archive(self, temp_dir, mock_settings):
        """Test failure with corrupted archive."""
        archive_path = temp_dir / "corrupted.zip"
        # Create a file that looks like a zip but is corrupted
        with open(archive_path, "w") as f:
            f.write("This is not a valid zip file")

        target_path = temp_dir / "target"

        with pytest.raises(HTTPException) as exc_info:
            await extract_minecraft_server(str(archive_path), str(target_path))

        # Should get 400 with Chinese error message about corrupted archive
        assert exc_info.value.status_code == 400
        assert "压缩包文件损坏或格式不支持" in exc_info.value.detail


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

            with pytest.raises(HTTPException) as exc_info:
                await extract_minecraft_server(str(archive_path), str(target_path))

            # Should get 500 with Chinese error message about 7z not being available
            assert exc_info.value.status_code == 500
            assert "7z未安装或不可用" in exc_info.value.detail
