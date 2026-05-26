"""Tests for the archive SHA256 SSE endpoint."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app


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
    def create_pending_upload(
        self, client: TestClient, filename: str, content: bytes
    ) -> str:
        response = client.post(
            "/archive/upload/init",
            headers={"Authorization": "Bearer test_master_token"},
            json={"path": "/", "filename": filename, "size": len(content)},
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
            content=content,
        )
        assert chunk_response.status_code == 200
        assert chunk_response.json()["pending_verification"] is True
        return upload_id

    def test_calculate_pending_upload_sha256_success(
        self, client, mock_archive_settings
    ):
        temp_archive_dir = mock_archive_settings
        test_content = b"This is test content for SHA256 calculation"
        upload_id = self.create_pending_upload(client, "test_file.zip", test_content)
        expected_hash = hashlib.sha256(test_content).hexdigest()

        response = client.get(
            f"/archive/upload/{upload_id}/sha256/stream",
            headers={"Authorization": "Bearer test_master_token"},
        )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        assert events[0]["event_type"] == "start"
        assert events[-1]["event_type"] == "complete"
        assert events[-1]["filename"] == "test_file.zip"
        assert events[-1]["sha256"] == expected_hash
        assert not (temp_archive_dir / "test_file.zip").exists()

    def test_calculate_sha256_nonexistent_upload(self, client, mock_archive_settings):
        response = client.get(
            "/archive/upload/not-found/sha256/stream",
            headers={"Authorization": "Bearer test_master_token"},
        )

        assert response.status_code == 404
        assert "Upload session not found" in response.json()["detail"]

    def test_calculate_sha256_requires_completed_upload(
        self, client, mock_archive_settings
    ):
        response = client.post(
            "/archive/upload/init",
            headers={"Authorization": "Bearer test_master_token"},
            json={"path": "/", "filename": "incomplete.zip", "size": 10},
        )
        upload_id = response.json()["upload_id"]

        response = client.get(
            f"/archive/upload/{upload_id}/sha256/stream",
            headers={"Authorization": "Bearer test_master_token"},
        )

        assert response.status_code == 409
        assert "Upload is not complete" in response.json()["detail"]

    def test_unauthorized_access(self, client, mock_archive_settings):
        response = client.get("/archive/upload/test-upload/sha256/stream")

        assert response.status_code in [401, 422]

    def test_verify_sha256_success_publishes_file(self, client, mock_archive_settings):
        temp_archive_dir = mock_archive_settings
        test_content = b"publish after SHA256"
        upload_id = self.create_pending_upload(client, "publish.zip", test_content)
        expected_hash = hashlib.sha256(test_content).hexdigest()

        response = client.get(
            f"/archive/upload/{upload_id}/sha256/stream",
            headers={"Authorization": "Bearer test_master_token"},
        )
        assert response.status_code == 200

        verify_response = client.post(
            f"/archive/upload/{upload_id}/verify",
            headers={"Authorization": "Bearer test_master_token"},
            json={"sha256": expected_hash},
        )

        assert verify_response.status_code == 200
        assert verify_response.json()["path"] == "/publish.zip"
        assert (temp_archive_dir / "publish.zip").read_bytes() == test_content

    def test_verify_requires_server_sha256(self, client, mock_archive_settings):
        test_content = b"no server hash yet"
        upload_id = self.create_pending_upload(client, "no_hash.zip", test_content)

        verify_response = client.post(
            f"/archive/upload/{upload_id}/verify",
            headers={"Authorization": "Bearer test_master_token"},
            json={"sha256": hashlib.sha256(test_content).hexdigest()},
        )

        assert verify_response.status_code == 409
        assert "Server SHA256 has not completed" in verify_response.json()["detail"]

    def test_verify_sha256_mismatch_removes_pending_upload(
        self, client, mock_archive_settings
    ):
        temp_archive_dir = mock_archive_settings
        test_content = b"mismatched content"
        upload_id = self.create_pending_upload(client, "mismatch.zip", test_content)

        response = client.get(
            f"/archive/upload/{upload_id}/sha256/stream",
            headers={"Authorization": "Bearer test_master_token"},
        )
        assert response.status_code == 200

        verify_response = client.post(
            f"/archive/upload/{upload_id}/verify",
            headers={"Authorization": "Bearer test_master_token"},
            json={"sha256": hashlib.sha256(b"different").hexdigest()},
        )

        assert verify_response.status_code == 409
        assert "SHA256 mismatch" in verify_response.json()["detail"]
        assert not (temp_archive_dir / "mismatch.zip").exists()

        status_response = client.head(
            f"/archive/upload/{upload_id}",
            headers={"Authorization": "Bearer test_master_token"},
        )
        assert status_response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
