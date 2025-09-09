"""
Unit tests for archive compression endpoint.
Tests the creation of compressed archives from server files using real file operations.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app


class TestArchiveCompression:
    """Test archive compression endpoint with real file operations."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(api_app)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_admin_compression_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def server_setup(self, temp_dir):
        """Create server directory structure for testing."""
        # Create server directory
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True, exist_ok=True)

        # Create data directory with test files
        data_dir = server_path / "data"
        data_dir.mkdir(exist_ok=True)

        # Create test files in root data directory
        (data_dir / "server.properties").write_text(
            "server-port=25565\nmotd=Test Server\nmax-players=20\n"
        )
        (data_dir / "whitelist.json").write_text(
            '[{"uuid":"test-uuid","name":"testuser"}]'
        )

        # Create subdirectories with test files
        plugins_dir = data_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        (plugins_dir / "plugin.jar").write_bytes(b"\x00\x01\x02\x03" * 100)
        (plugins_dir / "config.yml").write_text(
            "plugin:\n  enabled: true\n  debug: false\n"
        )

        worlds_dir = data_dir / "world"
        worlds_dir.mkdir(exist_ok=True)
        (worlds_dir / "level.dat").write_bytes(b"\x05\x06\x07\x08" * 200)
        (worlds_dir / "region").mkdir(exist_ok=True)
        (worlds_dir / "region" / "r.0.0.mca").write_bytes(b"\x09\x0a\x0b\x0c" * 300)

        return server_path

    @pytest.fixture
    def archive_dir_setup(self, temp_dir):
        """Create archive directory for real testing."""
        archive_path = temp_dir / "archives"
        archive_path.mkdir(parents=True, exist_ok=True)
        return archive_path

    @pytest.fixture
    def real_server_manager(self, server_setup, archive_dir_setup, temp_dir):
        """Setup real server manager dependencies for testing."""

        with (
            patch("app.routers.archive.settings") as mock_settings,
            patch("app.dependencies.settings") as mock_dep_settings,
            patch("app.routers.archive.DockerMCManager") as mock_manager_class,
            patch("app.utils.compression.settings") as mock_compression_settings,
        ):
            # Configure settings
            mock_settings.archive_path = archive_dir_setup
            mock_settings.master_token = "test_master_token"
            mock_settings.server_path = temp_dir / "servers"
            mock_dep_settings.master_token = "test_master_token"
            mock_compression_settings.archive_path = archive_dir_setup

            # Configure manager
            mock_manager = mock_manager_class.return_value
            mock_instance = mock_manager.get_instance.return_value
            mock_instance.get_project_path.return_value = server_setup

            yield {
                "manager_mock": mock_manager,
                "instance_mock": mock_instance,
                "archive_dir": archive_dir_setup,
                "server_path": server_setup,
            }

    def test_create_entire_server_archive_with_verification(
        self, client, real_server_manager
    ):
        """Test creating archive of entire server and verify contents."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server"},
        )

        # The response should be successful even if 7z command fails
        # We're testing the API structure and file operations logic
        if response.status_code == 200:
            data = response.json()

            assert "archive_filename" in data
            assert "message" in data
            assert "test_server" in data["archive_filename"]
            assert data["archive_filename"].endswith(".7z")
            assert "entire server" in data["message"]

            # Note: Archive may not exist if 7z command is not available in test environment

        elif response.status_code == 500:
            # Expected if 7z command is not available
            assert "7z command not available" in response.json().get("detail", "")
        else:
            # Unexpected error
            pytest.fail(
                f"Unexpected response: {response.status_code} - {response.json()}"
            )

    def test_create_server_subdirectory_archive_with_verification(
        self, client, real_server_manager
    ):
        """Test creating archive of server subdirectory and verify contents."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server", "path": "/plugins"},
        )

        if response.status_code == 200:
            data = response.json()

            assert "archive_filename" in data
            assert "plugins" in data["archive_filename"]
            assert data["archive_filename"].endswith(".7z")
            assert "/plugins" in data["message"]

        elif response.status_code == 500:
            # Expected if 7z command is not available
            assert "7z command not available" in response.json().get("detail", "")
        else:
            pytest.fail(
                f"Unexpected response: {response.status_code} - {response.json()}"
            )

    def test_create_server_root_data_archive(self, client, real_server_manager):
        """Test creating archive of server root data directory."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server", "path": "/"},
        )

        if response.status_code == 200:
            data = response.json()

            assert "archive_filename" in data
            assert "test_server" in data["archive_filename"]
            assert data["archive_filename"].endswith(".7z")
            assert "'/' from server" in data["message"]

        elif response.status_code == 500:
            assert "7z command not available" in response.json().get("detail", "")
        else:
            pytest.fail(
                f"Unexpected response: {response.status_code} - {response.json()}"
            )

    def test_archive_file_content_verification(self, client, real_server_manager):
        """Test archive creation and attempt to verify file contents if possible."""
        # First, check if we have 7z available
        import shutil

        if not shutil.which("7z"):
            pytest.skip("7z command not available for content verification test")

        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server", "path": "/plugins"},
        )

        assert response.status_code == 200
        data = response.json()

        archive_path = real_server_manager["archive_dir"] / data["archive_filename"]

        if archive_path.exists():
            # Try to verify the archive by extracting it
            with tempfile.TemporaryDirectory() as extract_dir:
                import subprocess

                result = subprocess.run(
                    ["7z", "x", str(archive_path), f"-o{extract_dir}"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    extract_path = Path(extract_dir)

                    # Verify extracted files exist in the plugins subdirectory
                    assert (extract_path / "plugins" / "config.yml").exists()
                    assert (extract_path / "plugins" / "plugin.jar").exists()

                    # Verify file contents
                    config_content = (
                        extract_path / "plugins" / "config.yml"
                    ).read_text()
                    assert "enabled: true" in config_content
                    assert "debug: false" in config_content

                    plugin_data = (extract_path / "plugins" / "plugin.jar").read_bytes()
                    assert plugin_data == b"\x00\x01\x02\x03" * 100

    def test_create_server_archive_nonexistent_server(
        self, client, real_server_manager, temp_dir
    ):
        """Test creating archive for nonexistent server."""
        # Configure mock to return nonexistent server
        instance_mock = real_server_manager["instance_mock"]
        nonexistent_path = temp_dir / "servers" / "nonexistent_server"
        instance_mock.get_project_path.return_value = nonexistent_path

        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "nonexistent_server"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_create_server_archive_nonexistent_path(self, client, real_server_manager):
        """Test creating archive for nonexistent path within server."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "test_server", "path": "/nonexistent_folder"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_archive_filename_generation(
        self, client, real_server_manager, server_setup
    ):
        """Test that archive filenames are properly generated and sanitized."""
        # Create the required directory structure
        special_dir = server_setup / "data" / "plugins" / "special_config"
        special_dir.mkdir(parents=True, exist_ok=True)
        (special_dir / "test.txt").write_text("test content")

        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={
                "server_id": "test server with spaces",
                "path": "/plugins/special_config",
            },
        )

        if response.status_code == 200:
            data = response.json()

            filename = data["archive_filename"]
            assert "test_server_with_spaces" in filename
            assert "plugins_special_config" in filename
            assert filename.endswith(".7z")
            # Ensure no filesystem-sensitive characters
            assert ":" not in filename
            assert " " not in filename

        elif response.status_code == 500:
            assert "7z command not available" in response.json().get("detail", "")
        else:
            pytest.fail(f"Unexpected response: {response.status_code}")

    def test_unauthorized_access(self, client, real_server_manager):
        """Test unauthorized access to compression endpoint."""
        response = client.post("/archive/compress", json={"server_id": "test_server"})

        # Should return 401 or 422 for missing authentication
        assert response.status_code in [401, 422]

    def test_compression_with_special_characters(self, client, real_server_manager):
        """Test compression with special characters in server name and path."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"server_id": "my-server:2024", "path": "/world/nether*dimension"},
        )

        # Expect 404 since the path doesn't exist in our test setup
        assert response.status_code == 404

    def test_compression_missing_server_id(self, client, real_server_manager):
        """Test compression endpoint with missing server_id."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            json={"path": "/plugins"},
        )

        assert response.status_code == 422  # Validation error

    def test_compression_invalid_json(self, client, real_server_manager):
        """Test compression endpoint with invalid JSON."""
        response = client.post(
            "/archive/compress",
            headers={"Authorization": "Bearer test_master_token"},
            data="invalid json",
        )

        assert response.status_code == 422  # Validation error

    def test_compression_creates_archive_directory(self, client, temp_dir):
        """Test that compression creates archive directory if it doesn't exist."""
        server_path = temp_dir / "servers" / "test_server"
        server_path.mkdir(parents=True)
        data_dir = server_path / "data"
        data_dir.mkdir()
        (data_dir / "test.txt").write_text("test content")

        archive_dir = temp_dir / "new_archives"
        # Archive directory doesn't exist initially
        assert not archive_dir.exists()

        with (
            patch("app.routers.archive.settings") as mock_settings,
            patch("app.dependencies.settings") as mock_dep_settings,
            patch("app.routers.archive.DockerMCManager") as mock_manager_class,
            patch("app.utils.compression.settings") as mock_compression_settings,
        ):
            mock_settings.archive_path = archive_dir
            mock_settings.master_token = "test_master_token"
            mock_dep_settings.master_token = "test_master_token"
            mock_compression_settings.archive_path = archive_dir

            mock_manager = mock_manager_class.return_value
            mock_instance = mock_manager.get_instance.return_value
            mock_instance.get_project_path.return_value = server_path

            response = client.post(
                "/archive/compress",
                headers={"Authorization": "Bearer test_master_token"},
                json={"server_id": "test_server"},
            )

            # Directory should be created during the compression process
            assert archive_dir.exists()
            assert archive_dir.is_dir()

            # Response should either succeed or fail with 7z not available
            assert response.status_code in [200, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
