"""
Tests for multi-file upload API endpoints.
Tests the FastAPI endpoints for multi-file upload functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestMultiFileUploadAPI:
    """Test multi-file upload API endpoints."""

    @pytest.fixture
    def test_client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_admin_api_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_auth_headers(self):
        """Mock authentication headers."""
        return {"Authorization": "Bearer test_token"}

    @pytest.fixture
    def server_id(self):
        """Test server ID."""
        return "test_server"

    def test_check_multi_file_upload_success(self, test_client, mock_auth_headers, server_id, temp_dir):
        """Test successful conflict checking."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test request
                request_data = {
                    "files": [
                        {
                            "path": "config.properties",
                            "name": "config.properties",
                            "type": "file",
                            "size": 100
                        },
                        {
                            "path": "plugins",
                            "name": "plugins",
                            "type": "directory"
                        }
                    ]
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/check?path=/",
                    json=request_data,
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "session_id" in data
                assert "conflicts" in data
                assert isinstance(data["conflicts"], list)

    def test_check_multi_file_upload_server_not_found(self, test_client, mock_auth_headers, server_id):
        """Test conflict checking with non-existent server."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance that doesn't exist
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=False)
                mock_manager.get_instance.return_value = mock_instance

                request_data = {
                    "files": [
                        {
                            "path": "test.txt",
                            "name": "test.txt",
                            "type": "file",
                            "size": 100
                        }
                    ]
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/check?path=/",
                    json=request_data,
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 404
                assert "not found" in response.json()["detail"]

    def test_set_multi_file_upload_policy_success(self, test_client, mock_auth_headers, server_id, temp_dir):
        """Test successful policy setting."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # First create a session
                request_data = {
                    "files": [
                        {
                            "path": "config.properties",
                            "name": "config.properties",
                            "type": "file",
                            "size": 100
                        }
                    ]
                }

                check_response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/check?path=/",
                    json=request_data,
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                session_id = check_response.json()["session_id"]

                # Set policy
                policy_data = {
                    "mode": "always_overwrite"
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/policy",
                    json=policy_data,
                    params={"session_id": session_id},
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 200
                assert "successfully" in response.json()["message"]

    def test_set_multi_file_upload_policy_invalid_session(self, test_client, mock_auth_headers, server_id):
        """Test setting policy with invalid session."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_manager.get_instance.return_value = mock_instance

                policy_data = {
                    "mode": "always_overwrite"
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/policy",
                    json=policy_data,
                    params={"session_id": "invalid_session"},
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 404
                assert "session not found" in response.json()["detail"]

    def test_upload_multiple_files_success(self, test_client, mock_auth_headers, server_id, temp_dir):
        """Test successful multi-file upload."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # First create a session
                request_data = {
                    "files": [
                        {
                            "path": "test1.txt",
                            "name": "test1.txt",
                            "type": "file",
                            "size": 100
                        },
                        {
                            "path": "test2.txt",
                            "name": "test2.txt",
                            "type": "file",
                            "size": 200
                        }
                    ]
                }

                check_response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/check?path=/",
                    json=request_data,
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                session_id = check_response.json()["session_id"]

                # Set policy
                policy_data = {
                    "mode": "always_overwrite"
                }

                test_client.post(
                    f"/api/servers/{server_id}/files/upload/policy",
                    json=policy_data,
                    params={"session_id": session_id},
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                # Upload files
                files = [
                    ("files", ("test1.txt", b"content1", "text/plain")),
                    ("files", ("test2.txt", b"content2", "text/plain"))
                ]

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/multiple",
                    files=files,
                    params={"session_id": session_id, "path": "/"},
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert "Upload completed" in data["message"]
                assert "results" in data

    def test_upload_multiple_files_invalid_session(self, test_client, mock_auth_headers, server_id):
        """Test uploading with invalid session."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_manager.get_instance.return_value = mock_instance

                files = [
                    ("files", ("test.txt", b"content", "text/plain"))
                ]

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/multiple",
                    files=files,
                    params={"session_id": "invalid_session", "path": "/"},
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 404
                assert "session not found" in response.json()["detail"]

    def test_upload_multiple_files_server_not_found(self, test_client, mock_auth_headers, server_id):
        """Test uploading to non-existent server."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance that doesn't exist
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=False)
                mock_manager.get_instance.return_value = mock_instance

                files = [
                    ("files", ("test.txt", b"content", "text/plain"))
                ]

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/multiple",
                    files=files,
                    params={"session_id": "dummy_session", "path": "/"},
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 404
                assert "not found" in response.json()["detail"]

    def test_request_validation_invalid_file_type(self, test_client, mock_auth_headers, server_id):
        """Test request validation with invalid file type."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_manager.get_instance.return_value = mock_instance

                # Invalid file type
                request_data = {
                    "files": [
                        {
                            "path": "test.txt",
                            "name": "test.txt",
                            "type": "invalid_type",  # Invalid type
                            "size": 100
                        }
                    ]
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/check?path=/",
                    json=request_data,
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 422  # Validation error

    def test_request_validation_missing_fields(self, test_client, mock_auth_headers, server_id):
        """Test request validation with missing required fields."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_manager.get_instance.return_value = mock_instance

                # Missing required fields
                request_data = {
                    "files": [
                        {
                            "path": "test.txt",
                            # Missing name and type
                            "size": 100
                        }
                    ]
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/check?path=/",
                    json=request_data,
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 422  # Validation error

    def test_policy_validation_per_file_without_decisions(self, test_client, mock_auth_headers, server_id, temp_dir):
        """Test policy validation for per_file mode without decisions."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create existing file for conflict
                test_file = temp_dir / "existing.txt"
                test_file.write_text("existing content")

                # First create a session with conflicts
                request_data = {
                    "files": [
                        {
                            "path": "existing.txt",
                            "name": "existing.txt",
                            "type": "file",
                            "size": 100
                        }
                    ]
                }

                check_response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/check?path=/",
                    json=request_data,
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                session_id = check_response.json()["session_id"]

                # Try to set per_file policy without decisions
                policy_data = {
                    "mode": "per_file"
                    # Missing decisions
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/upload/policy",
                    json=policy_data,
                    params={"session_id": session_id},
                    headers={**mock_auth_headers, "Authorization": "Bearer test_master_token"}
                )

                assert response.status_code == 400
                assert "Decisions required" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__])