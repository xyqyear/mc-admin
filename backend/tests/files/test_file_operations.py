from tests.support.runtime import patch_settings
from tests.support.tasks import task_result

"""
Comprehensive unit tests for file operations API endpoints.
Tests file management functionality using temporary directories.
"""
import os
import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.background_tasks import TaskType
from app.main import api_app
from app.operations.journal import OperationJournal
from app.servers.models import Server


def setup_test_structure(instance):
    data = instance.get_data_path()
    data.mkdir(parents=True)
    (instance.get_project_path() / "docker-compose.yml").write_text("services: {}\n")
    (data / "server.properties").write_text("# Test server properties\nserver-port=25565\n")
    (data / "bukkit.yml").write_text("# Test bukkit config\nsettings:\n  allow-end: true\n")
    (data / "readme.txt").write_text("This is a test file.\nLine 2 of the test file.\n")
    (data / "binary.jar").write_bytes(b"\x00\x01\x02\x03\x04\x05")
    (data / "plugins").mkdir()
    (data / "world").mkdir()
    (data / "plugins/config.yml").write_text("plugin-config: true\n")
    (data / "plugins/plugin.jar").write_bytes(b"\x00\x01\x02\x03")
    (data / "world/level.dat").write_bytes(b"\x01\x02\x03\x04")


@contextmanager
def file_operations_settings():
    with patch_settings() as settings:
        settings.master_token = "test_master_token"
        yield


@pytest.fixture
async def ownership_journal(database, isolated_runtime):
    async with database.session_factory() as session:
        session.add(Server(server_id="test_server"))
        await session.commit()
    isolated_runtime.journal = OperationJournal(database.session_factory)
    return isolated_runtime.journal


class TestFileOperations:
    """Test file operations API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        with TestClient(api_app, raise_server_exceptions=False) as client:
            yield client

    @pytest.fixture
    def server_instance(self, isolated_runtime):
        server_id = "test_server"
        instance = isolated_runtime.docker_mc_manager.get_instance(server_id)
        setup_test_structure(instance)
        return server_id, instance

    def test_list_files_root(self, client, server_instance):
        """Test listing files in root directory."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.get(
                f"/servers/{server_id}/files",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            assert "items" in data
            assert "current_path" in data
            assert data["current_path"] == "/"

            # Check that items are returned (sorting will be handled by frontend)
            items = data["items"]
            assert len(items) > 0

            # Collect directories and files for verification
            directories = [item for item in items if item["type"] == "directory"]
            files = [item for item in items if item["type"] == "file"]

            # Check specific files exist
            file_names = [f["name"] for f in files]
            file_names_set = set(file_names)
            assert "server.properties" in file_names_set
            assert "bukkit.yml" in file_names_set
            assert "readme.txt" in file_names_set
            assert "binary.jar" in file_names_set

            # Check directory names
            dir_names = [d["name"] for d in directories]
            dir_names_set = set(dir_names)
            assert "plugins" in dir_names_set
            assert "world" in dir_names_set

    def test_list_files_subdirectory(self, client, server_instance):
        """Test listing files in subdirectory."""
        server_id, _ = server_instance

        with file_operations_settings():
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

    def test_list_files_nonexistent_path(self, client, server_instance):
        """Test listing files in nonexistent directory."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.get(
                f"/servers/{server_id}/files?path=/nonexistent",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []

    def test_get_file_content(self, client, server_instance):
        """Test getting file content."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.get(
                f"/servers/{server_id}/files/content?path=/server.properties",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            data = response.json()

            assert "content" in data
            assert "server-port=25565" in data["content"]
            assert "# Test server properties" in data["content"]

    def test_get_file_content_nonexistent(self, client, server_instance):
        """Test getting content of nonexistent file."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.get(
                f"/servers/{server_id}/files/content?path=/nonexistent.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "File not found" in response.json()["detail"]

    def test_update_file_content(self, client, server_instance):
        """Test updating file content."""
        server_id, instance = server_instance

        with file_operations_settings():
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
            file_path = instance.get_data_path() / "server.properties"
            assert file_path.read_text() == new_content

    def test_denied_file_open_preserves_content(self, client, server_instance):
        """A denied write must not change existing file bytes."""
        server_id, instance = server_instance

        target = instance.get_data_path() / "server.properties"
        original = target.read_bytes()
        with (
            file_operations_settings(),
            patch('aiofiles.open', side_effect=PermissionError('denied')),
        ):
            # Mock file write to raise an exception
            response = client.post(
                f"/servers/{server_id}/files/content?path=/server.properties",
                headers={"Authorization": "Bearer test_master_token"},
                json={"content": "new content"},
            )

            assert response.status_code == 500
            assert response.json()["detail"] == "服务器内部错误，请稍后重试"
        assert target.read_bytes() == original

    def test_download_file(self, client, server_instance):
        """Test downloading a file."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.get(
                f"/servers/{server_id}/files/download?path=/server.properties",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/octet-stream"
            assert "server-port=25565" in response.text

    def test_single_file_upload_endpoint_removed(self, client, server_instance):
        """Test legacy single-file upload endpoint is not exposed."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/upload?path=/",
                headers={"Authorization": "Bearer test_master_token"},
                files={"file": ("test_upload.txt", b"content", "text/plain")},
            )

            assert response.status_code == 404

    def test_create_file(self, client, server_instance):
        """Test creating a new file."""
        server_id, instance = server_instance

        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "new_config.yml", "type": "file", "path": "/"},
            )

            assert response.status_code == 200
            assert "created successfully" in response.json()["message"]

            # Verify file was created
            new_file = instance.get_data_path() / "new_config.yml"
            assert new_file.exists()
            assert new_file.is_file()

    def test_create_directory(self, client, server_instance):
        """Test creating a new directory."""
        server_id, instance = server_instance

        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "new_directory", "type": "directory", "path": "/"},
            )

            assert response.status_code == 200
            assert "created successfully" in response.json()["message"]

            # Verify directory was created
            new_dir = instance.get_data_path() / "new_directory"
            assert new_dir.exists()
            assert new_dir.is_dir()

    def test_create_file_already_exists(self, client, server_instance):
        """Test creating file that already exists."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/create",
                headers={"Authorization": "Bearer test_master_token"},
                json={"name": "server.properties", "type": "file", "path": "/"},
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_delete_file(self, client, server_instance):
        """Test deleting a file."""
        server_id, instance = server_instance

        with file_operations_settings():
            response = client.delete(
                f"/servers/{server_id}/files?path=/readme.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert task_result(client, response)["path"]

            # Verify file was deleted
            deleted_file = instance.get_data_path() / "readme.txt"
            assert not deleted_file.exists()

    def test_delete_directory(self, client, server_instance):
        """Test deleting a directory."""
        server_id, instance = server_instance

        with file_operations_settings():
            response = client.delete(
                f"/servers/{server_id}/files?path=/world",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert task_result(client, response)["path"]

            # Verify directory was deleted
            deleted_dir = instance.get_data_path() / "world"
            assert not deleted_dir.exists()

    def test_delete_nonexistent_file(self, client, server_instance):
        """Test deleting nonexistent file."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.delete(
                f"/servers/{server_id}/files?path=/nonexistent.txt",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_rename_file(self, client, server_instance):
        """Test renaming a file."""
        server_id, instance = server_instance

        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/readme.txt", "new_name": "renamed_readme.txt"},
            )

            assert response.status_code == 200
            assert "renamed successfully" in response.json()["message"]

            # Verify file was renamed
            old_file = instance.get_data_path() / "readme.txt"
            new_file = instance.get_data_path() / "renamed_readme.txt"
            assert not old_file.exists()
            assert new_file.exists()

    def test_rename_directory(self, client, server_instance):
        """Test renaming a directory."""
        server_id, instance = server_instance

        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/plugins", "new_name": "renamed_plugins"},
            )

            assert response.status_code == 200
            assert "renamed successfully" in response.json()["message"]

            # Verify directory was renamed
            old_dir = instance.get_data_path() / "plugins"
            new_dir = instance.get_data_path() / "renamed_plugins"
            assert not old_dir.exists()
            assert new_dir.exists()
            assert new_dir.is_dir()

    def test_rename_to_existing_name(self, client, server_instance):
        """Test renaming to existing name."""
        server_id, _ = server_instance

        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/rename",
                headers={"Authorization": "Bearer test_master_token"},
                json={"old_path": "/readme.txt", "new_name": "server.properties"},
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    def test_restore_file_ownership(self, client, server_instance, ownership_journal):
        server_id, instance = server_instance
        data = instance.get_data_path()
        target = data / "readme.txt"
        before = target.read_bytes()
        root_owner = (data.stat().st_uid, data.stat().st_gid)
        outside = instance.get_project_path() / "unselected.txt"
        outside.write_text("preserved outside data")
        if os.geteuid() == 0:
            os.chown(target, 65534, 65534)
        outside_owner = (outside.stat().st_uid, outside.stat().st_gid)
        with file_operations_settings():
            response = client.post(
                f"/servers/{server_id}/files/ownership/restore",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert response.status_code == 200
            task_id = response.json()["task_id"]
            deadline = time.monotonic() + 10
            while True:
                observed = client.get(f"/tasks/{task_id}", headers={"Authorization": "Bearer test_master_token"})
                assert observed.status_code == 200
                task = observed.json()
                if task["status"] in {"completed", "failed", "cancelled"}:
                    break
                assert time.monotonic() < deadline, task
                time.sleep(0.01)
            assert task["status"] == "completed", task
            assert task["task_type"] == TaskType.FILE_OWNERSHIP_REPAIR.value
            assert task["result"] == {"uid": root_owner[0], "gid": root_owner[1]}
        assert target.read_bytes() == before
        assert (target.stat().st_uid, target.stat().st_gid) == root_owner
        assert outside.read_text() == "preserved outside data"
        assert (outside.stat().st_uid, outside.stat().st_gid) == outside_owner

    def test_restore_file_ownership_server_not_found(self, client):
        """Test restoring file ownership on nonexistent server."""
        with file_operations_settings():
            response = client.post(
                "/servers/nonexistent/files/ownership/restore",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_server_not_found(self, client):
        """Test operations on nonexistent server."""
        # Mock instance that doesn't exist
        with file_operations_settings():
            response = client.get(
                "/servers/nonexistent/files",
                headers={"Authorization": "Bearer test_master_token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_unauthorized_access(self, client, server_instance):
        """Test unauthorized access to file operations."""
        server_id, _ = server_instance

        response = client.get(f"/servers/{server_id}/files")

        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__])
