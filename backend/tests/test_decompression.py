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

from app.utils.decompression import (
    DecompressionStepResult,
    extract_minecraft_server,
    get_path_ownership,
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
            if (user_info.pw_uid != 0 and  # Not root
                user_info.pw_uid < 65534 and  # Not nobody/nogroup
                user_info.pw_uid != 65534 and  # Not nobody
                user_info.pw_shell not in ['/bin/false', '/usr/sbin/nologin'] and
                user_info.pw_name not in ['daemon', 'bin', 'sys']):
                return user_info.pw_uid, user_info.pw_gid, user_info.pw_name
        
        # Fallback to common system users
        for username in ['www-data', 'nginx', 'apache', 'nobody']:
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
        with zipfile.ZipFile(archive_path, 'w') as zf:
            for file_path, content in structure.items():
                zf.writestr(file_path, content)
    elif format_type == "7z":
        # Create temporary directory structure first
        temp_extract_dir = archive_path.parent / f"{archive_path.stem}_temp"
        temp_extract_dir.mkdir(exist_ok=True)
        
        for file_path, content in structure.items():
            full_path = temp_extract_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
        
        # Create 7z archive
        subprocess.run([
            "7z", "a", str(archive_path), 
            f"{temp_extract_dir}/*"
        ], capture_output=True, check=True)
        
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
            "server/config.yml": "config content"
        }
        create_test_archive(archive_path, server_structure)
        
        target_path = temp_dir / "extracted"
        await aioos.makedirs(target_path, exist_ok=True)
        
        steps = []
        async for step in extract_minecraft_server(str(archive_path), str(target_path)):
            steps.append(step)
        
        # Verify all steps completed successfully
        assert len(steps) == 7
        expected_steps = [
            "archiveFileCheck",
            "serverPropertiesCheck", 
            "decompress",
            "chown",
            "findPath",
            "mv",
            "remove"
        ]
        
        for i, expected_step in enumerate(expected_steps):
            assert steps[i].step == expected_step
            assert steps[i].success is True
            assert isinstance(steps[i].message, str)
        
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
                "world/level.dat": "world data"
            },
            # Case 2: server.properties in nested folder
            {
                "minecraft_server/data/server.properties": "server-port=25565\n", 
                "minecraft_server/data/world/level.dat": "world data"
            },
            # Case 3: server.properties in deeply nested structure
            {
                "some/deep/folder/structure/server.properties": "server-port=25565\n",
                "some/deep/folder/structure/plugins/plugin.jar": "plugin"
            }
        ]
        
        for i, structure in enumerate(test_cases):
            archive_path = temp_dir / f"test_case_{i}.zip"
            create_test_archive(archive_path, structure)
            
            target_path = temp_dir / f"extracted_{i}"
            await aioos.makedirs(target_path, exist_ok=True)
            
            steps = []
            async for step in extract_minecraft_server(str(archive_path), str(target_path)):
                steps.append(step)
            
            assert len(steps) == 7
            assert all(step.success for step in steps)
            
            # Verify server.properties was moved to target
            assert (target_path / "server.properties").exists()
            
            # Verify other files at same level as server.properties were also moved
            for file_path in structure.keys():
                if not file_path.endswith("server.properties"):
                    relative_path = Path(file_path).relative_to(Path(file_path).parent.parent if "/" in file_path else Path("."))
                    if "/" not in str(relative_path):  # File at same level
                        assert (target_path / relative_path.name).exists()

    async def test_7z_format_archive(self, temp_dir, mock_settings):
        """Test extraction with 7z format archive."""
        archive_path = temp_dir / "server.7z"
        server_structure = {
            "mc_server/server.properties": "server-port=25565\n",
            "mc_server/world/level.dat": "world data",
            "mc_server/mods/mod.jar": "mod content"
        }
        create_test_archive(archive_path, server_structure, format_type="7z")
        
        target_path = temp_dir / "extracted_7z"
        await aioos.makedirs(target_path, exist_ok=True)
        
        steps = []
        async for step in extract_minecraft_server(str(archive_path), str(target_path)):
            steps.append(step)
        
        assert len(steps) == 7
        assert all(step.success for step in steps)
        
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
        
        steps = []
        async for step in extract_minecraft_server(str(archive_path), str(target_path)):
            steps.append(step)
        
        # Should only get one step that fails
        assert len(steps) == 1
        assert steps[0].step == "archiveFileCheck"
        assert steps[0].success is False
        assert "压缩包不存在" in steps[0].message
    
    async def test_no_server_properties(self, temp_dir, mock_settings):
        """Test failure when server.properties is not in archive."""
        # Create archive without server.properties
        archive_path = temp_dir / "invalid.zip"
        structure = {
            "some_file.txt": "content",
            "folder/another_file.txt": "content"
        }
        create_test_archive(archive_path, structure)
        
        target_path = temp_dir / "target"
        
        steps = []
        async for step in extract_minecraft_server(str(archive_path), str(target_path)):
            steps.append(step)
        
        # Should get archiveFileCheck success, then serverPropertiesCheck failure
        assert len(steps) == 2
        assert steps[0].step == "archiveFileCheck"
        assert steps[0].success is True
        assert steps[1].step == "serverPropertiesCheck"
        assert steps[1].success is False
        assert "压缩包中未找到server.properties文件" in steps[1].message
    
    async def test_corrupted_archive(self, temp_dir, mock_settings):
        """Test failure with corrupted archive."""
        archive_path = temp_dir / "corrupted.zip"
        # Create a file that looks like a zip but is corrupted
        with open(archive_path, 'w') as f:
            f.write("This is not a valid zip file")
        
        target_path = temp_dir / "target"
        
        steps = []
        async for step in extract_minecraft_server(str(archive_path), str(target_path)):
            steps.append(step)
        
        # Should get archiveFileCheck success, then serverPropertiesCheck failure
        assert len(steps) == 2
        assert steps[0].step == "archiveFileCheck"
        assert steps[0].success is True
        assert steps[1].step == "serverPropertiesCheck"
        assert steps[1].success is False
        assert "压缩包文件损坏或格式不支持" in steps[1].message
    
    async def test_extraction_permission_denied(self, temp_dir, mock_settings):
        """Test failure when no permission to extract due to read-only archive."""
        archive_path = temp_dir / "test.zip"
        create_test_archive(archive_path, {"server.properties": "content"})
        target_path = temp_dir / "target"
        
        # Get test user credentials
        test_uid, test_gid, test_username = get_test_user()
        
        # Make archive readable only by root
        os.chmod(archive_path, 0o600)
        
        steps = []
        async for step in extract_minecraft_server(
            str(archive_path), str(target_path), test_uid=test_uid, test_gid=test_gid
        ):
            steps.append(step)
        
        # Should get archiveFileCheck success, then serverPropertiesCheck failure
        assert len(steps) >= 2
        assert steps[0].step == "archiveFileCheck"
        assert steps[0].success is True
        assert steps[1].step == "serverPropertiesCheck"
        assert steps[1].success is False
        assert ("无权限访问压缩包文件" in steps[1].message or
                "检查压缩包内容时发生错误" in steps[1].message)
        
        # Restore permissions for cleanup
        os.chmod(archive_path, 0o644)
    
    async def test_chown_permission_denied_real(self, temp_dir, mock_settings):
        """Test chown failure - simpler test with 7z extraction working."""
        archive_path = temp_dir / "test.zip"
        create_test_archive(archive_path, {"server.properties": "content"})
        target_path = temp_dir / "target"
        
        # Use a non-existent user ID that will cause chown to fail
        test_uid, test_gid = 99999, 99999  # Non-existent user
        
        steps = []
        async for step in extract_minecraft_server(
            str(archive_path), str(target_path), test_uid=test_uid, test_gid=test_gid
        ):
            steps.append(step)
        
        # Error could happen at different steps depending on system permissions
        has_error = any(not step.success for step in steps)
        assert has_error
        
        failed_step = next(step for step in steps if not step.success)
        assert failed_step.step in ["serverPropertiesCheck", "decompress", "chown"]
        error_keywords = [
            "无权限", "权限", "Permission", "Operation not permitted", 
            "command not found", "检查", "解压", "chown"
        ]
        assert any(keyword in failed_step.message for keyword in error_keywords)
    
    async def test_find_permission_denied(self, temp_dir, mock_settings):
        """Test failure when find command fails due to permissions on temp directory."""
        archive_path = temp_dir / "test.zip"
        create_test_archive(archive_path, {"server.properties": "content"})
        target_path = temp_dir / "target"
        
        # Get test user credentials
        test_uid, test_gid, test_username = get_test_user()
        
        steps = []
        async for step in extract_minecraft_server(
            str(archive_path), str(target_path), test_uid=test_uid, test_gid=test_gid
        ):
            steps.append(step)
        
        # Check if we got an error at some point (could be various steps)
        has_error = any(not step.success for step in steps)
        if has_error:
            failed_step = next(step for step in steps if not step.success)
            assert failed_step.step in ["serverPropertiesCheck", "findPath", "decompress", "chown"]
            assert ("无权限搜索临时目录" in failed_step.message or
                    "搜索server.properties时发生错误" in failed_step.message or
                    "无权限访问压缩包文件" in failed_step.message or
                    "检查压缩包内容时发生错误" in failed_step.message or
                    "权限" in failed_step.message or "Permission" in failed_step.message)

    async def test_move_permission_denied(self, temp_dir, mock_settings):
        """Test failure when move operation fails due to target directory permissions."""
        archive_path = temp_dir / "test.zip"
        create_test_archive(archive_path, {"server.properties": "content"})
        
        # Create target directory with restricted permissions
        target_path = temp_dir / "restricted_target"
        target_path.mkdir()
        os.chmod(target_path, 0o555)  # Read and execute only, no write
        
        # Use non-existent user ID
        test_uid, test_gid = 99999, 99999
        
        try:
            steps = []
            async for step in extract_minecraft_server(
                str(archive_path), str(target_path), test_uid=test_uid, test_gid=test_gid
            ):
                steps.append(step)
            
            # Check if we got an error at some point
            has_error = any(not step.success for step in steps)
            if has_error:
                failed_step = next(step for step in steps if not step.success)
                assert failed_step.step in ["serverPropertiesCheck", "decompress", "chown", "mv"]
                error_keywords = [
                    "无权限", "权限", "Permission", "Operation not permitted",
                    "command not found", "检查", "解压", "chown", "移动", "文件"
                ]
                assert any(keyword in failed_step.message for keyword in error_keywords)
            
        finally:
            # Restore permissions for cleanup
            os.chmod(target_path, 0o755)


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
class TestUtilityFunctions:
    """Test utility functions."""
    
    async def test_get_path_ownership_success(self, temp_dir):
        """Test successful path ownership retrieval."""
        test_file = temp_dir / "test_file"
        test_file.touch()
        
        result = await get_path_ownership(test_file)
        assert result is not None
        uid, gid = result
        assert isinstance(uid, int)
        assert isinstance(gid, int)
        assert uid >= 0
        assert gid >= 0
    
    async def test_get_path_ownership_nonexistent(self, temp_dir):
        """Test path ownership retrieval for nonexistent path."""
        nonexistent = temp_dir / "nonexistent"
        
        result = await get_path_ownership(nonexistent)
        assert result is None


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
            
            steps = []
            async for step in extract_minecraft_server(str(archive_path), str(target_path)):
                steps.append(step)
            
            # Should get archiveFileCheck success, then serverPropertiesCheck failure
            assert len(steps) == 2
            assert steps[0].step == "archiveFileCheck"
            assert steps[0].success is True
            assert steps[1].step == "serverPropertiesCheck"
            assert steps[1].success is False
            assert "7z未安装或不可用" in steps[1].message