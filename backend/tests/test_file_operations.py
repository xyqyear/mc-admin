"""
Comprehensive unit tests for file operations API endpoints.
Tests file management functionality using temporary directories.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


class MockMCInstance:
    """Mock MCInstance for testing file operations."""

    def __init__(self, server_id: str, base_path: Path):
        self.server_id = server_id
        self.base_path = base_path
        self.project_path = base_path / server_id
        self.data_path = self.project_path / "data"

    def get_project_path(self) -> Path:
        """Return the project path."""
        return self.project_path

    async def exists(self):
        """Return True to indicate server exists."""
        return True

    def setup_test_structure(self):
        """Create test file and directory structure."""
        # Create base directories
        self.data_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        (self.data_path / "server.properties").write_text(
            "# Test server properties\nserver-port=25565\n"
        )
        (self.data_path / "bukkit.yml").write_text(
            "# Test bukkit config\nsettings:\n  allow-end: true\n"
        )
        (self.data_path / "readme.txt").write_text(
            "This is a test file.\nLine 2 of the test file.\n"
        )
        (self.data_path / "binary.jar").write_bytes(b"\x00\x01\x02\x03\x04\x05")

        # Create directories
        (self.data_path / "plugins").mkdir(exist_ok=True)
        (self.data_path / "world").mkdir(exist_ok=True)
        (self.data_path / "logs").mkdir(exist_ok=True)

        # Create nested files
        (self.data_path / "plugins" / "config.yml").write_text("plugin-config: true\n")
        (self.data_path / "plugins" / "plugin.jar").write_bytes(b"\x00\x01\x02\x03")
        (self.data_path / "world" / "level.dat").write_bytes(b"\x01\x02\x03\x04")
        (self.data_path / "logs" / "latest.log").write_text(
            "[INFO] Server starting...\n[INFO] Server started\n"
        )


class TestFileOperations:
    """Test file operations API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_server_file_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_instance(self, temp_dir):
        """Create mock instance with test structure."""
        server_id = "test_server"
        instance = MockMCInstance(server_id, temp_dir)
        instance.setup_test_structure()
        return server_id, instance

    def test_list_files_root(self, client, mock_instance):
        """Test listing files in root directory."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            assert "items" in data
            assert "current_path" in data
            assert data["current_path"] == "/"

            # Check that items are sorted (directories first, then files, both alphabetical)
            items = data["items"]
            assert len(items) > 0

            # Should have directories first
            directories = [item for item in items if item["type"] == "directory"]
            files = [item for item in items if item["type"] == "file"]

            # Directories should be alphabetically sorted
            dir_names = [d["name"] for d in directories]
            assert dir_names == sorted(dir_names, key=str.lower)

            # Files should be alphabetically sorted
            file_names = [f["name"] for f in files]
            assert file_names == sorted(file_names, key=str.lower)

            # Check specific files exist
            file_names_set = set(file_names)
            assert "server.properties" in file_names_set
            assert "bukkit.yml" in file_names_set
            assert "readme.txt" in file_names_set

            # Check directory names
            dir_names_set = set(dir_names)
            assert "plugins" in dir_names_set
            assert "world" in dir_names_set
            assert "logs" in dir_names_set

    def test_list_files_subdirectory(self, client, mock_instance):
        """Test listing files in subdirectory."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files?path=/plugins",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            assert data["current_path"] == "/plugins"
            items = data["items"]

            item_names = [item["name"] for item in items]
            assert "config.yml" in item_names
            assert "plugin.jar" in item_names

    def test_list_files_nonexistent_path(self, client, mock_instance):
        """Test listing files in nonexistent directory."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files?path=/nonexistent",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []

    def test_file_classification(self, client, mock_instance):
        """Test file type classification (config, editable)."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()
            items = {item["name"]: item for item in data["items"]}

            # server.properties should be config and editable
            assert items["server.properties"]["is_config"] is True
            assert items["server.properties"]["is_editable"] is True

            # bukkit.yml should be config and editable
            assert items["bukkit.yml"]["is_config"] is True
            assert items["bukkit.yml"]["is_editable"] is True

            # readme.txt should be config and editable (text file)
            assert items["readme.txt"]["is_config"] is True
            assert items["readme.txt"]["is_editable"] is True

            # binary.jar should not be config or editable
            assert items["binary.jar"]["is_config"] is False
            assert items["binary.jar"]["is_editable"] is False

    def test_get_file_content(self, client, mock_instance):
        """Test getting file content."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files/content?path=/server.properties",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            assert "content" in data
            assert "server-port=25565" in data["content"]
            assert "# Test server properties" in data["content"]

    def test_get_file_content_noneditable(self, client, mock_instance):
        """Test getting content of non-editable file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files/content?path=/binary.jar",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 400
            assert "File is not editable" in response.json()["detail"]

    def test_get_file_content_nonexistent(self, client, mock_instance):
        """Test getting content of nonexistent file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files/content?path=/nonexistent.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "File not found" in response.json()["detail"]

    def test_update_file_content(self, client, mock_instance):
        """Test updating file content."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            new_content = (
                "# Updated server properties\nserver-port=25566\nmax-players=20\n"
            )

            response = client.post(
                f"/servers/{server_id}/files/content?path=/server.properties",
                headers={"Authorization": "Bearer test_master_token"},
                json={"content": new_content},
            )

            assert response.status_code == 200
            assert "File updated successfully" in response.json()["message"]

            # Verify content was actually updated
            file_path = instance.data_path / "server.properties"
            assert file_path.read_text() == new_content

    def test_update_file_content_backup_on_error(self, client, mock_instance):
        """Test that backup is restored on write error."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            # Mock file write to raise an exception
            with patch("builtins.open", side_effect=Exception("Write error")):
                response = client.post(
                    f"/servers/{server_id}/files/content?path=/server.properties",
                    headers={"Authorization": "Bearer test_master_token"},
                    json={"content": "new content"},
                )

                assert response.status_code == 500
                assert "Failed to update file" in response.json()["detail"]

    def test_download_file(self, client, mock_instance):
        """Test downloading a file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                f"/servers/{server_id}/files/download?path=/server.properties",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/octet-stream"
            assert "server-port=25565" in response.text

    def test_upload_file(self, client, mock_instance):
        """Test uploading a file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            # Create test file content
            test_content = b"This is test file content for upload"

            response = client.post(
                f"/servers/{server_id}/files/upload?path=/",
                headers={"Authorization": "Bearer test_master_token"},
                files={"file": ("test_upload.txt", test_content, "text/plain")},
            )

            assert response.status_code == 200
            assert "uploaded successfully" in response.json()["message"]

            # Verify file was created
            uploaded_file = instance.data_path / "test_upload.txt"
            assert uploaded_file.exists()
            assert uploaded_file.read_bytes() == test_content

    def test_upload_file_to_subdirectory(self, client, mock_instance):
        """Test uploading a file to subdirectory."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            test_content = b"Plugin configuration"

            response = client.post(
                f"/servers/{server_id}/files/upload?path=/plugins",
                headers={"Authorization": "Bearer test_master_token"},
                files={"file": ("new_plugin.yml", test_content, "text/yaml")},
            )

            assert response.status_code == 200

            # Verify file was created in subdirectory
            uploaded_file = instance.data_path / "plugins" / "new_plugin.yml"
            assert uploaded_file.exists()
            assert uploaded_file.read_bytes() == test_content

    def test_upload_file_already_exists(self, client, mock_instance):
        """Test uploading file that already exists."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.post(
                f"/servers/{server_id}/files/upload?path=/",
                headers={"Authorization": "Bearer test_master_token"},
                files={"file": ("server.properties", b"content", "text/plain")},
            )

            assert response.status_code == 409
            assert "File already exists" in response.json()["detail"]

    def test_create_file(self, client, mock_instance):
        """Test creating a new file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.post(
                f"/servers/{server_id}/files/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "new_config.yml", "type": "file", "path": "/"},
            )

            assert response.status_code == 200
            assert "created successfully" in response.json()["message"]

            # Verify file was created
            new_file = instance.data_path / "new_config.yml"
            assert new_file.exists()
            assert new_file.is_file()

    def test_create_directory(self, client, mock_instance):
        """Test creating a new directory."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.post(
                f"/servers/{server_id}/files/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "new_directory", "type": "directory", "path": "/"},
            )

            assert response.status_code == 200
            assert "created successfully" in response.json()["message"]

            # Verify directory was created
            new_dir = instance.data_path / "new_directory"
            assert new_dir.exists()
            assert new_dir.is_dir()

    def test_create_file_already_exists(self, client, mock_instance):
        """Test creating file that already exists."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.post(
                f"/servers/{server_id}/files/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "server.properties", "type": "file", "path": "/"},
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_delete_file(self, client, mock_instance):
        """Test deleting a file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.delete(
                f"/servers/{server_id}/files?path=/readme.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            assert "deleted successfully" in response.json()["message"]

            # Verify file was deleted
            deleted_file = instance.data_path / "readme.txt"
            assert not deleted_file.exists()

    def test_delete_directory(self, client, mock_instance):
        """Test deleting a directory."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.delete(
                f"/servers/{server_id}/files?path=/world",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            assert "deleted successfully" in response.json()["message"]

            # Verify directory was deleted
            deleted_dir = instance.data_path / "world"
            assert not deleted_dir.exists()

    def test_delete_nonexistent_file(self, client, mock_instance):
        """Test deleting nonexistent file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.delete(
                f"/servers/{server_id}/files?path=/nonexistent.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_rename_file(self, client, mock_instance):
        """Test renaming a file."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.post(
                f"/servers/{server_id}/files/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/readme.txt", "new_name": "renamed_readme.txt"},
            )

            assert response.status_code == 200
            assert "renamed successfully" in response.json()["message"]

            # Verify file was renamed
            old_file = instance.data_path / "readme.txt"
            new_file = instance.data_path / "renamed_readme.txt"
            assert not old_file.exists()
            assert new_file.exists()

    def test_rename_directory(self, client, mock_instance):
        """Test renaming a directory."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.post(
                f"/servers/{server_id}/files/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/plugins", "new_name": "renamed_plugins"},
            )

            assert response.status_code == 200
            assert "renamed successfully" in response.json()["message"]

            # Verify directory was renamed
            old_dir = instance.data_path / "plugins"
            new_dir = instance.data_path / "renamed_plugins"
            assert not old_dir.exists()
            assert new_dir.exists()
            assert new_dir.is_dir()

    def test_rename_to_existing_name(self, client, mock_instance):
        """Test renaming to existing name."""
        server_id, instance = mock_instance

        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            mock_manager.get_instance.return_value = instance
            mock_settings.master_token = "test_master_token"

            response = client.post(
                f"/servers/{server_id}/files/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/readme.txt", "new_name": "server.properties"},
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_server_not_found(self, client):
        """Test operations on nonexistent server."""
        with (
            patch("app.routers.servers.mc_manager") as mock_manager,
            patch("app.dependencies.settings") as mock_settings,
        ):
            # Mock instance that doesn't exist
            mock_instance = MockMCInstance("nonexistent", Path("/tmp"))

            async def mock_exists():
                return False

            mock_instance.exists = mock_exists  # type: ignore
            mock_manager.get_instance.return_value = mock_instance
            mock_settings.master_token = "test_master_token"

            response = client.get(
                "/servers/nonexistent/files",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_unauthorized_access(self, client, mock_instance):
        """Test unauthorized access to file operations."""
        server_id, instance = mock_instance

        response = client.get(f"/servers/{server_id}/files")

        # Should return 401 or 422 for missing authentication
        assert response.status_code in [401, 422]


if __name__ == "__main__":
    pytest.main([__file__])
