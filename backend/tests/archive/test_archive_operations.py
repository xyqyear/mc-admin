"""
Comprehensive unit tests for archive operations API endpoints.
Tests archive file management functionality using temporary directories.
"""

import hashlib
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app


@contextmanager
def mock_archive_operations_setup(archive_path: Path):
    """Context manager for mocking archive operations dependencies.

    Args:
        archive_path: The archive base path to use for testing

    Yields:
        None: The context is set up with mocked dependencies
    """
    with (
        patch("app.routers.archive.settings") as mock_settings,
        patch("app.dependencies.settings") as mock_dep_settings,
    ):
        mock_settings.archive_path = archive_path
        mock_settings.master_token = "test_master_token"
        mock_dep_settings.master_token = "test_master_token"
        yield


def parse_sse_events(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = "\n".join(
            line.removeprefix("data:").strip()
            for line in block.splitlines()
            if line.startswith("data:")
        )
        if data:
            events.append(json.loads(data))
    return events


def verify_archive_upload(client: TestClient, upload_id: str, content: bytes) -> dict:
    expected_hash = hashlib.sha256(content).hexdigest()
    sha_response = client.get(
        f"/archive/upload/{upload_id}/sha256/stream",
        headers={"Authorization": "Bearer test_master_token"},
    )
    assert sha_response.status_code == 200
    events = parse_sse_events(sha_response.text)
    assert events[-1]["sha256"] == expected_hash

    verify_response = client.post(
        f"/archive/upload/{upload_id}/verify",
        headers={"Authorization": "Bearer test_master_token"},
        json={"sha256": expected_hash},
    )
    assert verify_response.status_code == 200
    return verify_response.json()


class TestArchiveOperations:
    """Test archive operations API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(api_app)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_admin_archive_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def archive_setup(self, temp_dir):
        """Create archive directory with test structure."""
        archive_path = temp_dir / "archives"
        archive_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        (archive_path / "server.jar").write_bytes(b"\x00\x01\x02\x03\x04\x05" * 100)
        (archive_path / "config.yml").write_text(
            "# Test config\nserver:\n  port: 25565\n  motd: 'Test Server'\n"
        )
        (archive_path / "readme.txt").write_text(
            "This is a test archive file.\nIt contains some documentation.\n"
        )

        # Create directories
        (archive_path / "plugins").mkdir(exist_ok=True)
        (archive_path / "backups").mkdir(exist_ok=True)
        (archive_path / "worlds").mkdir(exist_ok=True)

        # Create nested files
        (archive_path / "plugins" / "essentials.jar").write_bytes(
            b"\x00\x01\x02\x03" * 50
        )
        (archive_path / "plugins" / "permissions.yml").write_text(
            "permissions:\n  default: true\n"
        )
        (archive_path / "backups" / "world_backup.zip").write_bytes(
            b"\x01\x02\x03\x04" * 200
        )
        (archive_path / "worlds" / "world.tar.gz").write_bytes(
            b"\x05\x06\x07\x08" * 150
        )

        return archive_path

    def test_list_archive_files_root(self, client, archive_setup):
        """Test listing files in archive root directory."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.get(
                "/archive",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            assert "items" in data
            assert "current_path" in data
            assert data["current_path"] == "/"

            # Check that items are returned
            items = data["items"]
            assert len(items) > 0

            # Collect directories and files for verification
            directories = [item for item in items if item["type"] == "directory"]
            files = [item for item in items if item["type"] == "file"]

            # Check specific files exist
            file_names = {f["name"] for f in files}
            assert "server.jar" in file_names
            assert "config.yml" in file_names
            assert "readme.txt" in file_names

            # Check directory names
            dir_names = {d["name"] for d in directories}
            assert "plugins" in dir_names
            assert "backups" in dir_names
            assert "worlds" in dir_names

    def test_list_archive_files_subdirectory(self, client, archive_setup):
        """Test listing files in archive subdirectory."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.get(
                "/archive?path=/plugins",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            assert data["current_path"] == "/plugins"
            items = data["items"]

            item_names = {item["name"] for item in items}
            assert "essentials.jar" in item_names
            assert "permissions.yml" in item_names

    def test_list_archive_files_nonexistent_path(self, client, archive_setup):
        """Test listing files in nonexistent directory."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.get(
                "/archive?path=/nonexistent",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []

    def test_download_archive_file(self, client, archive_setup):
        """Test downloading an archive file."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.get(
                "/archive/download?path=/config.yml",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/octet-stream"
            assert "server:" in response.text

    def test_resumable_upload_archive_file(self, client, archive_setup):
        """Test uploading an archive file with the resumable protocol."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            test_content = b"This is test file content for upload to archive"

            response = client.post(
                "/archive/upload/init",
                headers={"Authorization": "Bearer test_master_token"},
                json={
                    "path": "/",
                    "filename": "test_upload.txt",
                    "size": len(test_content),
                },
            )

            assert response.status_code == 200
            init_data = response.json()
            assert init_data["offset"] == 0
            assert init_data["chunk_size"] == 8 * 1024 * 1024
            upload_id = init_data["upload_id"]

            status_response = client.head(
                f"/archive/upload/{upload_id}",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert status_response.status_code == 204
            assert status_response.headers["upload-offset"] == "0"

            chunk_response = client.patch(
                f"/archive/upload/{upload_id}",
                headers={
                    "Authorization": "Bearer test_master_token",
                    "Upload-Offset": "0",
                    "Content-Type": "application/octet-stream",
                },
                content=test_content,
            )

            assert chunk_response.status_code == 200
            chunk_data = chunk_response.json()
            assert chunk_data["complete"] is True
            assert chunk_data["pending_verification"] is True
            assert chunk_data["offset"] == len(test_content)
            assert chunk_data["path"] == "/test_upload.txt"

            uploaded_file = archive_path / "test_upload.txt"
            assert not uploaded_file.exists()

            verify_data = verify_archive_upload(client, upload_id, test_content)
            assert verify_data["path"] == "/test_upload.txt"
            assert uploaded_file.exists()
            assert uploaded_file.read_bytes() == test_content

    def test_resumable_upload_archive_file_to_subdirectory(
        self, client, archive_setup
    ):
        """Test resumable upload to a subdirectory."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            test_content = b"New plugin jar file content"

            response = client.post(
                "/archive/upload/init",
                headers={"Authorization": "Bearer test_master_token"},
                json={
                    "path": "/plugins",
                    "filename": "new_plugin.jar",
                    "size": len(test_content),
                },
            )

            assert response.status_code == 200
            upload_id = response.json()["upload_id"]
            chunk_response = client.patch(
                f"/archive/upload/{upload_id}",
                headers={
                    "Authorization": "Bearer test_master_token",
                    "Upload-Offset": "0",
                    "Content-Type": "application/octet-stream",
                },
                content=test_content,
            )

            assert chunk_response.status_code == 200
            assert chunk_response.json()["path"] == "/plugins/new_plugin.jar"
            uploaded_file = archive_path / "plugins" / "new_plugin.jar"
            assert not uploaded_file.exists()

            verify_data = verify_archive_upload(client, upload_id, test_content)
            assert verify_data["path"] == "/plugins/new_plugin.jar"
            assert uploaded_file.exists()
            assert uploaded_file.read_bytes() == test_content

    def test_resumable_upload_archive_file_already_exists(self, client, archive_setup):
        """Test init rejects an existing target without overwrite."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.post(
                "/archive/upload/init",
                headers={"Authorization": "Bearer test_master_token"},
                json={"path": "/", "filename": "config.yml", "size": 7},
            )

            assert response.status_code == 409
            assert "File already exists" in response.json()["detail"]

    def test_resumable_upload_archive_file_with_overwrite(self, client, archive_setup):
        """Test resumable upload can overwrite when allowed."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            new_content = b"# Overwritten config content"

            response = client.post(
                "/archive/upload/init",
                headers={"Authorization": "Bearer test_master_token"},
                json={
                    "path": "/",
                    "filename": "config.yml",
                    "size": len(new_content),
                    "allow_overwrite": True,
                },
            )

            assert response.status_code == 200
            upload_id = response.json()["upload_id"]
            chunk_response = client.patch(
                f"/archive/upload/{upload_id}",
                headers={
                    "Authorization": "Bearer test_master_token",
                    "Upload-Offset": "0",
                    "Content-Type": "application/octet-stream",
                },
                content=new_content,
            )

            assert chunk_response.status_code == 200
            uploaded_file = archive_path / "config.yml"
            assert uploaded_file.read_text() != new_content.decode()

            verify_archive_upload(client, upload_id, new_content)
            assert uploaded_file.read_bytes() == new_content

    def test_resumable_upload_offset_mismatch(self, client, archive_setup):
        """Test chunk upload rejects stale or incorrect offsets."""
        with mock_archive_operations_setup(archive_setup):
            response = client.post(
                "/archive/upload/init",
                headers={"Authorization": "Bearer test_master_token"},
                json={"path": "/", "filename": "offset.zip", "size": 8},
            )
            upload_id = response.json()["upload_id"]

            mismatch_response = client.patch(
                f"/archive/upload/{upload_id}",
                headers={
                    "Authorization": "Bearer test_master_token",
                    "Upload-Offset": "4",
                    "Content-Type": "application/octet-stream",
                },
                content=b"data",
            )

            assert mismatch_response.status_code == 409
            assert mismatch_response.json()["detail"]["offset"] == 0

    def test_cancel_resumable_upload(self, client, archive_setup):
        """Test cancelling an upload removes its session."""
        with mock_archive_operations_setup(archive_setup):
            response = client.post(
                "/archive/upload/init",
                headers={"Authorization": "Bearer test_master_token"},
                json={"path": "/", "filename": "cancel.zip", "size": 4},
            )
            upload_id = response.json()["upload_id"]

            cancel_response = client.delete(
                f"/archive/upload/{upload_id}",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert cancel_response.status_code == 204

            status_response = client.head(
                f"/archive/upload/{upload_id}",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert status_response.status_code == 404

    def test_cancel_completed_upload_before_verification(self, client, archive_setup):
        """Test cancelling a completed upload before SHA256 publish removes temp state."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            test_content = b"pending upload"
            response = client.post(
                "/archive/upload/init",
                headers={"Authorization": "Bearer test_master_token"},
                json={
                    "path": "/",
                    "filename": "pending.zip",
                    "size": len(test_content),
                },
            )
            upload_id = response.json()["upload_id"]

            chunk_response = client.patch(
                f"/archive/upload/{upload_id}",
                headers={
                    "Authorization": "Bearer test_master_token",
                    "Upload-Offset": "0",
                    "Content-Type": "application/octet-stream",
                },
                content=test_content,
            )
            assert chunk_response.status_code == 200
            assert chunk_response.json()["pending_verification"] is True
            assert not (archive_path / "pending.zip").exists()

            cancel_response = client.delete(
                f"/archive/upload/{upload_id}",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert cancel_response.status_code == 204
            assert not (archive_path / "pending.zip").exists()

            sha_response = client.get(
                f"/archive/upload/{upload_id}/sha256/stream",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert sha_response.status_code == 404

    def test_create_archive_file(self, client, archive_setup):
        """Test creating a new archive file."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.post(
                "/archive/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "new_script.sh", "type": "file", "path": "/"},
            )

            assert response.status_code == 200
            assert "created successfully" in response.json()["message"]

            # Verify file was created
            new_file = archive_path / "new_script.sh"
            assert new_file.exists()
            assert new_file.is_file()

    def test_create_archive_directory(self, client, archive_setup):
        """Test creating a new archive directory."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.post(
                "/archive/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "new_folder", "type": "directory", "path": "/"},
            )

            assert response.status_code == 200
            assert "created successfully" in response.json()["message"]

            # Verify directory was created
            new_dir = archive_path / "new_folder"
            assert new_dir.exists()
            assert new_dir.is_dir()

    def test_create_archive_file_already_exists(self, client, archive_setup):
        """Test creating archive file that already exists."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.post(
                "/archive/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "config.yml", "type": "file", "path": "/"},
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_delete_archive_file(self, client, archive_setup):
        """Test deleting an archive file."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.delete(
                "/archive?path=/readme.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            assert "deleted successfully" in response.json()["message"]

            # Verify file was deleted
            deleted_file = archive_path / "readme.txt"
            assert not deleted_file.exists()

    def test_delete_archive_directory(self, client, archive_setup):
        """Test deleting an archive directory."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.delete(
                "/archive?path=/backups",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            assert "deleted successfully" in response.json()["message"]

            # Verify directory was deleted
            deleted_dir = archive_path / "backups"
            assert not deleted_dir.exists()

    def test_delete_nonexistent_archive_file(self, client, archive_setup):
        """Test deleting nonexistent archive file."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.delete(
                "/archive?path=/nonexistent.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_rename_archive_file(self, client, archive_setup):
        """Test renaming an archive file."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.post(
                "/archive/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/readme.txt", "new_name": "documentation.txt"},
            )

            assert response.status_code == 200
            assert "renamed successfully" in response.json()["message"]

            # Verify file was renamed
            old_file = archive_path / "readme.txt"
            new_file = archive_path / "documentation.txt"
            assert not old_file.exists()
            assert new_file.exists()

    def test_rename_archive_directory(self, client, archive_setup):
        """Test renaming an archive directory."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.post(
                "/archive/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/plugins", "new_name": "mods"},
            )

            assert response.status_code == 200
            assert "renamed successfully" in response.json()["message"]

            # Verify directory was renamed
            old_dir = archive_path / "plugins"
            new_dir = archive_path / "mods"
            assert not old_dir.exists()
            assert new_dir.exists()
            assert new_dir.is_dir()

    def test_rename_to_existing_archive_name(self, client, archive_setup):
        """Test renaming archive item to existing name."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.post(
                "/archive/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/readme.txt", "new_name": "config.yml"},
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_unauthorized_access(self, client, archive_setup):
        """Test unauthorized access to archive operations."""
        response = client.get("/archive")

        # Should return 401 or 422 for missing authentication
        assert response.status_code in [401, 422]

    def test_archive_directory_creation_on_access(self, client, temp_dir):
        """Test that archive directory is created automatically when accessed."""
        archive_path = temp_dir / "archives"

        # Ensure directory doesn't exist initially
        assert not archive_path.exists()

        with mock_archive_operations_setup(archive_path):
            response = client.get(
                "/archive",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            # Directory should be created automatically
            assert archive_path.exists()
            assert archive_path.is_dir()

    def test_archive_file_size_reporting(self, client, archive_setup):
        """Test that file sizes are correctly reported."""
        archive_path = archive_setup

        with mock_archive_operations_setup(archive_path):
            response = client.get(
                "/archive",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            # Find the server.jar file and check its size
            server_jar = next(
                item
                for item in data["items"]
                if item["name"] == "server.jar" and item["type"] == "file"
            )

            # Should report the actual file size (600 bytes from b"\x00\x01\x02\x03\x04\x05" * 100)
            assert server_jar["size"] == 600


if __name__ == "__main__":
    pytest.main([__file__])
