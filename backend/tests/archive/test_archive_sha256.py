"""Tests for the archive SHA256 endpoint."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app


@pytest.fixture
def client():
    return TestClient(api_app)


@pytest.fixture
def temp_archive_dir():
    with tempfile.TemporaryDirectory(prefix="archive_sha256_test_") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_archive_settings(temp_archive_dir):
    with (
        patch("app.routers.archive.settings") as mock_settings,
        patch("app.dependencies.settings") as mock_dep_settings,
    ):
        mock_settings.archive_path = temp_archive_dir
        mock_settings.master_token = "test_master_token"
        mock_dep_settings.master_token = "test_master_token"
        yield temp_archive_dir


class TestArchiveSHA256:
    def test_calculate_sha256_success(self, client, mock_archive_settings):
        temp_archive_dir = mock_archive_settings

        test_file = temp_archive_dir / "test_file.zip"
        test_content = b"This is test content for SHA256 calculation"
        test_file.write_bytes(test_content)

        import hashlib

        expected_hash = hashlib.sha256(test_content).hexdigest()

        response = client.get(
            "/archive/sha256?path=/test_file.zip",
            headers={"Authorization": "Bearer test_master_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "sha256" in data
        assert "filename" in data
        assert data["filename"] == "test_file.zip"
        assert data["sha256"] == expected_hash

    def test_calculate_sha256_nonexistent_file(self, client, mock_archive_settings):
        response = client.get(
            "/archive/sha256?path=/nonexistent.zip",
            headers={"Authorization": "Bearer test_master_token"},
        )

        assert response.status_code == 404
        assert "Archive file not found" in response.json()["detail"]

    def test_calculate_sha256_directory(self, client, mock_archive_settings):
        temp_archive_dir = mock_archive_settings

        test_dir = temp_archive_dir / "test_dir"
        test_dir.mkdir()

        response = client.get(
            "/archive/sha256?path=/test_dir",
            headers={"Authorization": "Bearer test_master_token"},
        )

        assert response.status_code == 400
        assert "Path is not a file" in response.json()["detail"]

    def test_unauthorized_access(self, client, mock_archive_settings):
        response = client.get("/archive/sha256?path=/test.zip")

        assert response.status_code in [401, 422]

    def test_calculate_sha256_nested_path(self, client, mock_archive_settings):
        temp_archive_dir = mock_archive_settings

        nested_dir = temp_archive_dir / "subdir"
        nested_dir.mkdir()

        test_file = nested_dir / "nested_file.zip"
        test_content = b"Nested file content for SHA256"
        test_file.write_bytes(test_content)

        import hashlib

        expected_hash = hashlib.sha256(test_content).hexdigest()

        response = client.get(
            "/archive/sha256?path=/subdir/nested_file.zip",
            headers={"Authorization": "Bearer test_master_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "nested_file.zip"
        assert data["sha256"] == expected_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
