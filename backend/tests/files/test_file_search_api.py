"""
Test file search API endpoint using FastAPI TestClient.
Tests the REST API endpoint for file search functionality with authentication.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestFileSearchAPI:
    """Test file search API endpoints."""

    @pytest.fixture
    def test_client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_admin_search_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def auth_headers(self):
        """Get authentication headers for API requests."""
        # Use master token for authentication in tests
        return {"Authorization": "Bearer test_master_token"}

    @pytest.fixture
    def server_id(self):
        """Test server ID."""
        return "test_server"

    def test_search_files_basic_regex(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test basic regex file search."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test files
                (temp_dir / "config.py").write_text("# Configuration\nDEBUG = True")
                (temp_dir / "main.py").write_text(
                    "# Main module\nfrom config import DEBUG"
                )
                (temp_dir / "README.md").write_text("# Project Documentation")

                # Test search request
                search_request = {"regex": r".*\.py$", "ignore_case": True}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search?path=/",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "query" in data
                assert "results" in data
                assert "total_count" in data
                assert "search_path" in data

                # Verify query was stored correctly
                assert data["query"]["regex"] == r".*\.py$"
                assert data["query"]["ignore_case"] is True

                # Verify results
                assert data["total_count"] == 2
                assert len(data["results"]) == 2

                # Verify file details
                file_names = {result["name"] for result in data["results"]}
                assert file_names == {"config.py", "main.py"}

                for result in data["results"]:
                    assert result["type"] == "file"
                    assert result["size"] > 0
                    assert "modified_at" in result
                    assert result["path"].startswith("/")

    def test_search_files_case_sensitivity(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test case sensitivity in file search."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test file with mixed case
                (temp_dir / "Config.PY").write_text("# Configuration")

                # Test case-insensitive search
                search_request = {"regex": r"config\.py", "ignore_case": True}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "Config.PY"

                # Test case-sensitive search
                search_request["ignore_case"] = False

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 0  # Should not match Config.PY

    def test_search_files_size_filters(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test file size filtering."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create files with different sizes
                (temp_dir / "small.txt").write_text("small")  # ~5 bytes
                (temp_dir / "large.txt").write_text("x" * 1000)  # 1000 bytes

                # Test min_size filter
                search_request = {"regex": r".*\.txt$", "min_size": 100}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "large.txt"
                assert data["results"][0]["size"] >= 100

                # Test max_size filter
                search_request = {"regex": r".*\.txt$", "max_size": 100}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "small.txt"
                assert data["results"][0]["size"] <= 100

    def test_search_files_date_filters(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test date filtering."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test file
                (temp_dir / "test.txt").write_text("test content")

                # Test newer_than filter (should find the file as it's just created)
                yesterday = datetime.now() - timedelta(days=1)
                search_request = {
                    "regex": r".*\.txt$",
                    "newer_than": yesterday.isoformat(),
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "test.txt"

                # Test older_than filter (should not find the file as it's just created)
                yesterday = datetime.now() - timedelta(days=1)
                search_request = {
                    "regex": r".*\.txt$",
                    "older_than": yesterday.isoformat(),
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 0  # File is newer than yesterday

    def test_search_files_combined_filters(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test combining multiple filters."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test files
                (temp_dir / "small_config.py").write_text("# Small config")  # ~14 bytes
                (temp_dir / "large_config.py").write_text(
                    "# " + "x" * 100
                )  # ~102 bytes
                (temp_dir / "small_script.sh").write_text("#!/bin/bash")  # ~11 bytes

                # Search for Python files larger than 50 bytes
                one_hour_ago = datetime.now() - timedelta(hours=1)
                search_request = {
                    "regex": r".*\.py$",
                    "min_size": 50,
                    "newer_than": one_hour_ago.isoformat(),
                    "ignore_case": False,
                }

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "large_config.py"
                assert data["results"][0]["size"] >= 50

    def test_search_files_custom_path(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test searching in a custom path."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create subdirectory structure
                config_dir = temp_dir / "config"
                config_dir.mkdir()
                (config_dir / "server.properties").write_text("server-port=25565")

                # Search in specific subdirectory
                search_request = {"regex": r".*\.properties$"}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search?path=/config",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["search_path"] == "/config"
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "server.properties"

    def test_search_files_empty_results(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test search that returns no results."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test file that won't match
                (temp_dir / "test.txt").write_text("content")

                # Search for Python files (should find none)
                search_request = {"regex": r".*\.py$"}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 0
                assert len(data["results"]) == 0

    def test_search_files_server_not_found(self, test_client, auth_headers):
        """Test searching for files on non-existent server."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance that doesn't exist
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=False)
                mock_manager.get_instance.return_value = mock_instance

                search_request = {"regex": r".*\.py$"}

                response = test_client.post(
                    "/api/servers/nonexistent_server/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()

    def test_search_files_unauthorized(self, test_client, server_id, temp_dir):
        """Test search without authentication."""
        with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
            # Setup mock instance
            mock_instance = MagicMock()
            mock_instance.exists = AsyncMock(return_value=True)
            mock_instance.get_data_path.return_value = temp_dir
            mock_manager.get_instance.return_value = mock_instance

            search_request = {"regex": r".*\.py$"}

            # Request without authentication headers
            response = test_client.post(
                f"/api/servers/{server_id}/files/search",
                json=search_request,
            )

            assert response.status_code == 401
            assert "detail" in response.json()

    def test_search_files_invalid_regex(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test search with invalid regex pattern."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Mock fd command to return error for invalid regex
                with patch("app.files.search._run_fd_command") as mock_fd:
                    mock_fd.side_effect = Exception("Invalid regular expression")

                    search_request = {"regex": r"[invalid regex("}

                    response = test_client.post(
                        f"/api/servers/{server_id}/files/search",
                        json=search_request,
                        headers=auth_headers,
                    )

                    assert response.status_code == 500
                    # Global exception handler now formats error messages differently
                    assert "Invalid regular expression" in response.json()["detail"]

    def test_search_files_invalid_request_body(
        self, test_client, auth_headers, server_id
    ):
        """Test search with invalid request body."""
        with patch("app.config.settings.master_token", "test_master_token"):
            # Missing required 'regex' field
            invalid_request = {"ignore_case": True}

            response = test_client.post(
                f"/api/servers/{server_id}/files/search",
                json=invalid_request,
                headers=auth_headers,
            )

            assert response.status_code == 422  # Validation error
            assert "detail" in response.json()

    def test_search_files_invalid_size_values(
        self, test_client, auth_headers, server_id
    ):
        """Test search with invalid size values."""
        with patch("app.config.settings.master_token", "test_master_token"):
            # Negative size values
            invalid_request = {"regex": r".*", "min_size": -100}

            response = test_client.post(
                f"/api/servers/{server_id}/files/search",
                json=invalid_request,
                headers=auth_headers,
            )

            assert response.status_code == 422  # Validation error
            assert "detail" in response.json()

    def test_search_files_invalid_datetime_format(
        self, test_client, auth_headers, server_id
    ):
        """Test search with invalid datetime format."""
        with patch("app.config.settings.master_token", "test_master_token"):
            invalid_request = {"regex": r".*", "newer_than": "invalid-datetime"}

            response = test_client.post(
                f"/api/servers/{server_id}/files/search",
                json=invalid_request,
                headers=auth_headers,
            )

            assert response.status_code == 422  # Validation error
            assert "detail" in response.json()

    def test_search_files_complex_regex_patterns(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test complex regex patterns."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test files
                (temp_dir / "test_file.py").write_text("# test")
                (temp_dir / "config.yml").write_text("config: value")
                (temp_dir / "backup_2023.tar.gz").write_text("backup")

                # Test complex regex - files starting with 'test' or ending with '.yml'
                search_request = {"regex": r"(^test.*|.*\.yml$)"}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 2

                found_files = {result["name"] for result in data["results"]}
                assert found_files == {"test_file.py", "config.yml"}

    def test_search_files_subfolders_enabled(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test API search with subfolders enabled."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test structure
                (temp_dir / "root.txt").write_text("root file")

                sub_dir = temp_dir / "subdir"
                sub_dir.mkdir()
                (sub_dir / "sub.txt").write_text("sub file")

                deep_dir = sub_dir / "deep"
                deep_dir.mkdir()
                (deep_dir / "deep.txt").write_text("deep file")

                # Search with subfolders enabled (explicit)
                search_request = {"regex": r".*\.txt$", "search_subfolders": True}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()

                # Verify query was stored correctly
                assert data["query"]["search_subfolders"] is True

                # Should find all 3 txt files
                assert data["total_count"] == 3
                found_files = {result["name"] for result in data["results"]}
                assert found_files == {"root.txt", "sub.txt", "deep.txt"}

    def test_search_files_subfolders_disabled(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test API search with subfolders disabled."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test structure
                (temp_dir / "root.txt").write_text("root file")

                sub_dir = temp_dir / "subdir"
                sub_dir.mkdir()
                (sub_dir / "sub.txt").write_text("sub file")

                deep_dir = sub_dir / "deep"
                deep_dir.mkdir()
                (deep_dir / "deep.txt").write_text("deep file")

                # Search with subfolders disabled
                search_request = {"regex": r".*\.txt$", "search_subfolders": False}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()

                # Verify query was stored correctly
                assert data["query"]["search_subfolders"] is False

                # Should find only the root file (max-depth 1)
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "root.txt"
                assert data["results"][0]["path"] == "/root.txt"

    def test_search_files_subfolders_default_behavior(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test that search_subfolders defaults to True in API."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create test structure
                (temp_dir / "root.txt").write_text("root file")

                sub_dir = temp_dir / "subdir"
                sub_dir.mkdir()
                (sub_dir / "sub.txt").write_text("sub file")

                # Search without specifying search_subfolders (should default to True)
                search_request = {"regex": r".*\.txt$"}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()

                # Verify default value
                assert data["query"]["search_subfolders"] is True

                # Should find both files (default behavior is to search subfolders)
                assert data["total_count"] == 2
                found_files = {result["name"] for result in data["results"]}
                assert found_files == {"root.txt", "sub.txt"}

    def test_search_files_subfolders_with_path_param(
        self, test_client, auth_headers, server_id, temp_dir
    ):
        """Test subfolder search control combined with custom search path."""
        with patch("app.config.settings.master_token", "test_master_token"):
            with patch("app.routers.servers.files.docker_mc_manager") as mock_manager:
                # Setup mock instance
                mock_instance = MagicMock()
                mock_instance.exists = AsyncMock(return_value=True)
                mock_instance.get_data_path.return_value = temp_dir
                mock_manager.get_instance.return_value = mock_instance

                # Create nested structure
                config_dir = temp_dir / "config"
                config_dir.mkdir()
                (config_dir / "server.properties").write_text("server-port=25565")

                plugins_dir = config_dir / "plugins"
                plugins_dir.mkdir()
                (plugins_dir / "plugin.yml").write_text("name: TestPlugin")

                # Search in config directory without subfolders
                search_request = {"regex": r".*\.properties$", "search_subfolders": False}

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search?path=/config",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["search_path"] == "/config"
                assert data["total_count"] == 1
                assert data["results"][0]["name"] == "server.properties"

                # Now search with subfolders enabled - should still find only .properties files
                search_request["search_subfolders"] = True

                response = test_client.post(
                    f"/api/servers/{server_id}/files/search?path=/config",
                    json=search_request,
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["total_count"] == 1  # Should still find only the .properties file
                assert data["results"][0]["name"] == "server.properties"

    def test_search_files_subfolders_invalid_value(
        self, test_client, auth_headers, server_id
    ):
        """Test search with invalid search_subfolders value."""
        with patch("app.config.settings.master_token", "test_master_token"):
            # Invalid boolean value
            invalid_request = {"regex": r".*", "search_subfolders": "not_a_boolean"}

            response = test_client.post(
                f"/api/servers/{server_id}/files/search",
                json=invalid_request,
                headers=auth_headers,
            )

            assert response.status_code == 422  # Validation error
            assert "detail" in response.json()
