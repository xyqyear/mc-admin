"""
Test for path conflict handling in multi-file upload functionality.
Tests the bug fix for conflict path calculation relative to current directory vs base directory.
"""

import tempfile
from pathlib import Path

import pytest

from app.common.file_operations import (
    FileStructureItem,
    MultiFileUploadRequest,
    OverwriteDecision,
    OverwritePolicy,
    check_upload_conflicts,
    set_upload_policy,
    upload_multiple_files,
)


class MockUploadFile:
    """Mock UploadFile for testing."""

    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._content):
            return b""
        if size == -1:
            result = self._content[self._pos :]
            self._pos = len(self._content)
            return result
        else:
            result = self._content[self._pos : self._pos + size]
            self._pos += size
            return result

    async def seek(self, position: int) -> None:
        self._pos = position


class TestPathConflictHandling:
    """Test path conflict handling for multi-file upload."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_admin_path_conflict_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def test_structure(self, temp_dir):
        """Create test file and directory structure."""
        base_path = temp_dir / "test_server"
        base_path.mkdir(parents=True, exist_ok=True)

        # Create existing files in root directory
        (base_path / "server.properties").write_text("root config")

        # Create existing files in subdirectory
        config_dir = base_path / "config"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "settings.yml").write_text("existing config settings")

        # Create existing files in nested subdirectory
        plugins_dir = base_path / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        mods_dir = plugins_dir / "mods"
        mods_dir.mkdir(exist_ok=True)
        (mods_dir / "mod.jar").write_bytes(b"existing mod")

        return base_path

    @pytest.mark.asyncio
    async def test_root_directory_conflicts(self, test_structure):
        """Test conflict detection when uploading to root directory."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="server.properties",
                    name="server.properties",
                    type="file",
                    size=200,
                ),
                FileStructureItem(
                    path="new_file.txt",
                    name="new_file.txt",
                    type="file",
                    size=100,
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)

        assert len(response.conflicts) == 1
        assert response.conflicts[0].path == "server.properties"

    @pytest.mark.asyncio
    async def test_subdirectory_conflicts(self, test_structure):
        """Test conflict detection when uploading to subdirectory."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="settings.yml",
                    name="settings.yml",
                    type="file",
                    size=150,
                ),
                FileStructureItem(
                    path="new_settings.yml",
                    name="new_settings.yml",
                    type="file",
                    size=120,
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/config", upload_request)

        assert len(response.conflicts) == 1
        # Path should be relative to upload path (/config), not base path
        assert response.conflicts[0].path == "settings.yml"

    @pytest.mark.asyncio
    async def test_nested_subdirectory_conflicts(self, test_structure):
        """Test conflict detection when uploading to nested subdirectory."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="mod.jar",
                    name="mod.jar",
                    type="file",
                    size=500,
                ),
                FileStructureItem(
                    path="new_mod.jar",
                    name="new_mod.jar",
                    type="file",
                    size=600,
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/plugins/mods", upload_request)

        assert len(response.conflicts) == 1
        # Path should be relative to upload path (/plugins/mods), not base path
        assert response.conflicts[0].path == "mod.jar"

    @pytest.mark.asyncio
    async def test_per_file_overwrite_subdirectory(self, test_structure):
        """Test per-file overwrite decisions work correctly with subdirectory paths."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="settings.yml",
                    name="settings.yml",
                    type="file",
                    size=150,
                ),
                FileStructureItem(
                    path="new_settings.yml",
                    name="new_settings.yml",
                    type="file",
                    size=120,
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/config", upload_request)
        session_id = response.session_id

        # Set per-file decision using the conflict path format
        decisions = [
            OverwriteDecision(path="settings.yml", overwrite=True),
        ]

        policy = OverwritePolicy(mode="per_file", decisions=decisions)
        await set_upload_policy(session_id, policy)

        # Create mock files
        files = [
            MockUploadFile("settings.yml", b"new config content"),
            MockUploadFile("new_settings.yml", b"new file content"),
        ]

        results = await upload_multiple_files(base_path, session_id, "/config", files)  # type: ignore

        assert len(results.results) == 2
        assert results.results["settings.yml"].status == "success"
        assert results.results["new_settings.yml"].status == "success"

        # Verify files were uploaded correctly
        settings_file = base_path / "config" / "settings.yml"
        new_settings_file = base_path / "config" / "new_settings.yml"

        assert settings_file.exists()
        assert new_settings_file.exists()
        assert settings_file.read_bytes() == b"new config content"
        assert new_settings_file.read_bytes() == b"new file content"

    @pytest.mark.asyncio
    async def test_mixed_directory_levels_conflicts(self, test_structure):
        """Test conflicts across multiple directory levels."""
        base_path = test_structure

        # Create files in different subdirectories within the upload structure
        upload_request = MultiFileUploadRequest(
            files=[
                # File in upload root (relative to /config)
                FileStructureItem(
                    path="settings.yml",
                    name="settings.yml",
                    type="file",
                    size=150,
                ),
                # File in subdirectory within upload path
                FileStructureItem(
                    path="plugins/plugin.yml",
                    name="plugin.yml",
                    type="file",
                    size=200,
                ),
                # New file with no conflict
                FileStructureItem(
                    path="new_config.yml",
                    name="new_config.yml",
                    type="file",
                    size=100,
                ),
            ],
        )

        # Create existing file in nested structure
        plugin_dir = base_path / "config" / "plugins"
        plugin_dir.mkdir(exist_ok=True)
        (plugin_dir / "plugin.yml").write_text("existing plugin config")

        response = await check_upload_conflicts(base_path, "/config", upload_request)

        assert len(response.conflicts) == 2
        conflict_paths = {conflict.path for conflict in response.conflicts}
        assert "settings.yml" in conflict_paths
        assert "plugins/plugin.yml" in conflict_paths


if __name__ == "__main__":
    pytest.main([__file__])