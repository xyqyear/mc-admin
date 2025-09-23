"""
Unit tests for multi-file upload functionality.
Tests the new multi-file and folder upload system with conflict detection and overwrite policies.
"""

import tempfile
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.common.file_operations import (
    FileStructureItem,
    MultiFileUploadRequest,
    OverwriteDecision,
    OverwritePolicy,
    UploadSession,
    check_upload_conflicts,
    get_upload_session,
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


class TestMultiFileUpload:
    """Test multi-file upload functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_admin_multi_upload_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def test_structure(self, temp_dir):
        """Create test file and directory structure."""
        base_path = temp_dir / "test_server"
        base_path.mkdir(parents=True, exist_ok=True)

        # Create existing files that might conflict
        (base_path / "config.properties").write_text("server.port=25565\n")
        (base_path / "server.jar").write_bytes(b"fake jar content")

        # Create existing directories
        (base_path / "plugins").mkdir(exist_ok=True)
        (base_path / "world").mkdir(exist_ok=True)

        # Create nested existing files
        (base_path / "plugins" / "existing_plugin.jar").write_bytes(b"existing plugin")
        (base_path / "world" / "level.dat").write_bytes(b"world data")

        return base_path

    @pytest.mark.asyncio
    async def test_check_upload_conflicts_no_conflicts(self, temp_dir):
        """Test checking for conflicts when no files would be overwritten."""
        base_path = temp_dir / "empty_server"
        base_path.mkdir(parents=True, exist_ok=True)

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=100,
                ),
                FileStructureItem(path="plugins", name="plugins", type="directory"),
                FileStructureItem(
                    path="plugins/new_plugin.jar",
                    name="new_plugin.jar",
                    type="file",
                    size=500,
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)

        assert response.session_id is not None
        assert len(response.conflicts) == 0

    @pytest.mark.asyncio
    async def test_check_upload_conflicts_with_conflicts(self, test_structure):
        """Test checking for conflicts when files would be overwritten."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                ),
                FileStructureItem(
                    path="server.jar", name="server.jar", type="file", size=1000
                ),
                FileStructureItem(
                    path="plugins/existing_plugin.jar",
                    name="existing_plugin.jar",
                    type="file",
                    size=300,
                ),
                FileStructureItem(
                    path="new_file.txt", name="new_file.txt", type="file", size=50
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)

        assert response.session_id is not None
        assert len(response.conflicts) == 3  # Three existing files

        conflict_paths = {conflict.path for conflict in response.conflicts}
        assert "config.properties" in conflict_paths
        assert "server.jar" in conflict_paths
        assert "plugins/existing_plugin.jar" in conflict_paths

        # Check that new file is not in conflicts
        assert "new_file.txt" not in conflict_paths

    @pytest.mark.asyncio
    async def test_set_upload_policy_always_overwrite(self, test_structure):
        """Test setting always overwrite policy."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                )
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="always_overwrite")
        await set_upload_policy(session_id, policy)

        session = get_upload_session(session_id)
        assert session is not None
        assert session.policy is not None
        assert session.policy.mode == "always_overwrite"

    @pytest.mark.asyncio
    async def test_set_upload_policy_never_overwrite(self, test_structure):
        """Test setting never overwrite policy."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                )
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="never_overwrite")
        await set_upload_policy(session_id, policy)

        session = get_upload_session(session_id)
        assert session is not None
        assert session.policy is not None
        assert session.policy.mode == "never_overwrite"

    @pytest.mark.asyncio
    async def test_set_upload_policy_per_file(self, test_structure):
        """Test setting per-file overwrite policy."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                ),
                FileStructureItem(
                    path="server.jar", name="server.jar", type="file", size=1000
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        # Create decisions for each conflict
        decisions = [
            OverwriteDecision(path="config.properties", overwrite=True),
            OverwriteDecision(path="server.jar", overwrite=False),
        ]

        policy = OverwritePolicy(mode="per_file", decisions=decisions)
        await set_upload_policy(session_id, policy)

        session = get_upload_session(session_id)
        assert session is not None
        assert session.policy is not None
        assert session.policy.mode == "per_file"
        assert len(session.policy.decisions or []) == 2

    @pytest.mark.asyncio
    async def test_set_upload_policy_per_file_missing_decisions(self, test_structure):
        """Test setting per-file policy without required decisions."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                )
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="per_file")  # No decisions provided

        with pytest.raises(HTTPException) as exc_info:
            await set_upload_policy(session_id, policy)

        assert exc_info.value.status_code == 400
        assert "Decisions required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_set_upload_policy_invalid_session(self):
        """Test setting policy for invalid session."""
        policy = OverwritePolicy(mode="always_overwrite")

        with pytest.raises(HTTPException) as exc_info:
            await set_upload_policy("invalid_session", policy)

        assert exc_info.value.status_code == 404
        assert "session not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upload_multiple_files_always_overwrite(self, test_structure):
        """Test uploading multiple files with always overwrite policy."""
        base_path = test_structure

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                ),
                FileStructureItem(
                    path="new_file.txt", name="new_file.txt", type="file", size=50
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="always_overwrite")
        await set_upload_policy(session_id, policy)

        # Create mock files
        files = [
            MockUploadFile("config.properties", b"new config content"),
            MockUploadFile("new_file.txt", b"new file content"),
        ]

        results = await upload_multiple_files(base_path, session_id, "/", files)  # type: ignore

        assert len(results.results) == 2
        assert results.results["config.properties"].status == "success"
        assert results.results["new_file.txt"].status == "success"

        # Verify files were uploaded
        config_file = base_path / "config.properties"
        new_file = base_path / "new_file.txt"

        assert config_file.exists()
        assert new_file.exists()
        assert config_file.read_bytes() == b"new config content"
        assert new_file.read_bytes() == b"new file content"

    @pytest.mark.asyncio
    async def test_upload_multiple_files_never_overwrite(self, test_structure):
        """Test uploading multiple files with never overwrite policy."""
        base_path = test_structure
        original_config_content = (base_path / "config.properties").read_bytes()

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                ),
                FileStructureItem(
                    path="new_file.txt", name="new_file.txt", type="file", size=50
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="never_overwrite")
        await set_upload_policy(session_id, policy)

        # Create mock files
        files = [
            MockUploadFile("config.properties", b"new config content"),
            MockUploadFile("new_file.txt", b"new file content"),
        ]

        results = await upload_multiple_files(base_path, session_id, "/", files)  # type: ignore

        assert len(results.results) == 2
        assert results.results["config.properties"].status == "skipped"
        assert results.results["config.properties"].reason == "exists"
        assert results.results["new_file.txt"].status == "success"

        # Verify existing file was not overwritten
        config_file = base_path / "config.properties"
        new_file = base_path / "new_file.txt"

        assert config_file.read_bytes() == original_config_content  # Not changed
        assert new_file.exists()
        assert new_file.read_bytes() == b"new file content"

    @pytest.mark.asyncio
    async def test_upload_multiple_files_per_file_decisions(self, test_structure):
        """Test uploading multiple files with per-file decisions."""
        base_path = test_structure
        original_server_content = (base_path / "server.jar").read_bytes()

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="config.properties",
                    name="config.properties",
                    type="file",
                    size=200,
                ),
                FileStructureItem(
                    path="server.jar", name="server.jar", type="file", size=1000
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        # Overwrite config but not server.jar
        decisions = [
            OverwriteDecision(path="config.properties", overwrite=True),
            OverwriteDecision(path="server.jar", overwrite=False),
        ]

        policy = OverwritePolicy(mode="per_file", decisions=decisions)
        await set_upload_policy(session_id, policy)

        # Create mock files
        files = [
            MockUploadFile("config.properties", b"new config content"),
            MockUploadFile("server.jar", b"new server jar content"),
        ]

        results = await upload_multiple_files(base_path, session_id, "/", files)  # type: ignore

        assert len(results.results) == 2
        assert results.results["config.properties"].status == "success"
        assert results.results["server.jar"].status == "skipped"
        assert results.results["server.jar"].reason == "exists"

        # Verify results
        config_file = base_path / "config.properties"
        server_file = base_path / "server.jar"

        assert config_file.read_bytes() == b"new config content"  # Overwritten
        assert server_file.read_bytes() == original_server_content  # Not changed

    @pytest.mark.asyncio
    async def test_upload_multiple_files_with_directories(self, temp_dir):
        """Test uploading files that require directory creation."""
        base_path = temp_dir / "empty_server"
        base_path.mkdir(parents=True, exist_ok=True)

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(path="mods", name="mods", type="directory"),
                FileStructureItem(
                    path="mods/my_mod.jar", name="my_mod.jar", type="file", size=500
                ),
                FileStructureItem(path="config", name="config", type="directory"),
                FileStructureItem(
                    path="config/settings.yml",
                    name="settings.yml",
                    type="file",
                    size=100,
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="always_overwrite")
        await set_upload_policy(session_id, policy)

        # Create mock files with full paths as filename
        files = [
            MockUploadFile("mods/my_mod.jar", b"mod content"),
            MockUploadFile("config/settings.yml", b"setting: value"),
        ]

        results = await upload_multiple_files(base_path, session_id, "/", files)  # type: ignore

        assert len(results.results) == 2
        assert results.results["mods/my_mod.jar"].status == "success"
        assert results.results["config/settings.yml"].status == "success"

        # Verify directories and files were created
        mods_dir = base_path / "mods"
        config_dir = base_path / "config"
        mod_file = base_path / "mods" / "my_mod.jar"
        settings_file = base_path / "config" / "settings.yml"

        assert mods_dir.exists() and mods_dir.is_dir()
        assert config_dir.exists() and config_dir.is_dir()
        assert mod_file.exists()
        assert settings_file.exists()
        assert mod_file.read_bytes() == b"mod content"
        assert settings_file.read_bytes() == b"setting: value"

    @pytest.mark.asyncio
    async def test_upload_multiple_files_missing_file(self, temp_dir):
        """Test uploading when a file is missing from the upload."""
        base_path = temp_dir / "test_server"
        base_path.mkdir(parents=True, exist_ok=True)

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="file1.txt", name="file1.txt", type="file", size=100
                ),
                FileStructureItem(
                    path="file2.txt", name="file2.txt", type="file", size=100
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="always_overwrite")
        await set_upload_policy(session_id, policy)

        # Only upload one of the two files
        files = [
            MockUploadFile("file1.txt", b"content1")
            # file2.txt is missing from upload
        ]

        results = await upload_multiple_files(base_path, session_id, "/", files)  # type: ignore

        # With the new implementation, we only process files that are actually uploaded
        # So we should only get results for file1.txt
        assert len(results.results) == 1
        assert results.results["file1.txt"].status == "success"

        # file2.txt is not in results because it wasn't uploaded

        # Verify only file1 was created
        file1 = base_path / "file1.txt"
        file2 = base_path / "file2.txt"

        assert file1.exists()
        assert not file2.exists()

    @pytest.mark.asyncio
    async def test_upload_multiple_files_invalid_session(self, temp_dir):
        """Test uploading with invalid session."""
        files = [MockUploadFile("test.txt", b"content")]

        with pytest.raises(HTTPException) as exc_info:
            await upload_multiple_files(temp_dir, "invalid_session", "/", files)  # type: ignore

        assert exc_info.value.status_code == 404
        assert "session not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upload_multiple_files_no_policy_set(self, temp_dir):
        """Test uploading without setting a policy."""
        base_path = temp_dir / "test_server"
        base_path.mkdir(parents=True, exist_ok=True)

        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(
                    path="test.txt", name="test.txt", type="file", size=100
                )
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        # Don't set a policy
        files = [MockUploadFile("test.txt", b"content")]

        with pytest.raises(HTTPException) as exc_info:
            await upload_multiple_files(base_path, session_id, "/", files)  # type: ignore

        assert exc_info.value.status_code == 400
        assert "Upload policy not set" in exc_info.value.detail

    def test_upload_session_expiry(self, temp_dir):
        """Test that upload sessions expire properly."""
        base_path = temp_dir / "test_server"
        base_path.mkdir(parents=True, exist_ok=True)

        # Manually create an expired session
        from app.common.file_operations import _SESSION_TIMEOUT, _upload_sessions

        session_id = "expired_session"
        expired_time = time.time() - _SESSION_TIMEOUT - 100  # Expired

        expired_session = UploadSession(
            session_id=session_id,
            conflicts=[],
            expires_at=expired_time,
            created_at=expired_time - 100,
        )

        _upload_sessions[session_id] = expired_session

        # Try to get the session - should be cleaned up
        session = get_upload_session(session_id)
        assert session is None

    @pytest.mark.asyncio
    async def test_upload_subdirectory_files_path_mapping(self, test_structure):
        """Test uploading files in subdirectories with correct path/name mapping."""
        base_path = test_structure

        # Test case that specifically tests the bug fix:
        # FileStructureItem with path="config/custom.yml" and name="custom.yml"
        # MockUploadFile with filename="custom.yml"
        upload_request = MultiFileUploadRequest(
            files=[
                FileStructureItem(path="config", name="config", type="directory"),
                FileStructureItem(
                    path="config/custom.yml",
                    name="custom.yml",  # This is just the filename, not the full path
                    type="file",
                    size=150,
                ),
                FileStructureItem(path="mods", name="mods", type="directory"),
                FileStructureItem(
                    path="mods/special_mod.jar",
                    name="special_mod.jar",  # This is just the filename, not the full path
                    type="file",
                    size=800,
                ),
            ],
        )

        response = await check_upload_conflicts(base_path, "/", upload_request)
        session_id = response.session_id

        policy = OverwritePolicy(mode="always_overwrite")
        await set_upload_policy(session_id, policy)

        # Create mock files with full paths as filename (as they would come from frontend)
        files = [
            MockUploadFile("config/custom.yml", b"custom config data"),
            MockUploadFile("mods/special_mod.jar", b"mod jar content"),
        ]

        # This should NOT produce "File not found in upload" errors anymore
        results = await upload_multiple_files(base_path, session_id, "/", files)  # type: ignore

        assert len(results.results) == 2

        # These should both be successful uploads, not "File not found" errors
        assert results.results["config/custom.yml"].status == "success"
        assert results.results["mods/special_mod.jar"].status == "success"

        # Verify the files were actually created in the correct subdirectories
        config_file = base_path / "config" / "custom.yml"
        mods_file = base_path / "mods" / "special_mod.jar"

        assert config_file.exists(), "Config file should exist"
        assert mods_file.exists(), "Mod file should exist"
        assert config_file.read_bytes() == b"custom config data"
        assert mods_file.read_bytes() == b"mod jar content"


if __name__ == "__main__":
    pytest.main([__file__])
