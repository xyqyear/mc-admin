from tests.support.runtime import patch_settings

"""Tests for the archive SHA256 SSE endpoint."""

import hashlib
import json
import tempfile
from pathlib import Path

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
        patch_settings() as mock_settings,
        patch_settings() as mock_dep_settings,
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


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_publisher", [False, True])
async def test_parallel_no_overwrite_publish_keeps_one_complete_result(tmp_path, monkeypatch, cancel_publisher):
    import asyncio

    from fastapi import HTTPException

    from app.archive import uploads
    from app.archive.application import archive_claims
    from app.operations.coordinator import ConflictPolicy, get_operation_coordinator

    target = tmp_path / "archives"
    target.mkdir()
    monkeypatch.setattr(uploads, "ARCHIVE_UPLOAD_TMP_DIR", tmp_path / "uploads")
    contents = (b"first archive", b"second archive")
    sessions = []
    for content in contents:
        session = await uploads.init_archive_upload(target, uploads.ArchiveUploadInitRequest(
            filename="shared.zip", size=len(content),
        ))
        await uploads.append_archive_upload_chunk(session.upload_id, 0, content)
        async for _ in uploads.iter_archive_upload_sha256_events(session.upload_id):
            pass
        sessions.append(session)

    original_copy = uploads.async_fs.copy2
    entered, release = asyncio.Event(), asyncio.Event()

    async def synchronize_copy(source, destination):
        await original_copy(source, destination)
        entered.set()
        await release.wait()

    monkeypatch.setattr(uploads.async_fs, "copy2", synchronize_copy)
    first = asyncio.create_task(uploads.verify_archive_upload(sessions[0].upload_id, uploads.ArchiveUploadVerifyRequest(sha256=hashlib.sha256(contents[0]).hexdigest())))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert not (target / "shared.zip").exists()
        second = asyncio.create_task(uploads.verify_archive_upload(sessions[1].upload_id, uploads.ArchiveUploadVerifyRequest(sha256=hashlib.sha256(contents[1]).hexdigest())))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), 0.05)
        if cancel_publisher:
            first.cancel()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(first), 0.05)
            first.cancel()
            assert not first.done()
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True), 5)
    if cancel_publisher:
        assert isinstance(results[0], asyncio.CancelledError)
    else:
        assert isinstance(results[0], uploads.ArchiveUploadVerifyResponse)
        assert results[0].path == "/shared.zip"
    assert isinstance(results[1], HTTPException)
    assert results[1].status_code == 409
    with pytest.raises(HTTPException) as occupied:
        await uploads.verify_archive_upload(sessions[1].upload_id, uploads.ArchiveUploadVerifyRequest(sha256=hashlib.sha256(contents[1]).hexdigest()))
    assert occupied.value.status_code == 409
    assert (target / "shared.zip").read_bytes() == contents[0]
    assert list(target.glob(".mc-admin-archive-*.tmp")) == []
    assert (await uploads.archive_upload_headers(sessions[1].upload_id))["Upload-State"] == "hashed"
    retained = await uploads._get_session(sessions[1].upload_id)
    assert retained.temp_path.read_bytes() == contents[1]
    with pytest.raises(HTTPException) as consumed:
        await uploads.archive_upload_headers(sessions[0].upload_id)
    assert consumed.value.status_code == 404
    async with get_operation_coordinator().acquire(await archive_claims(target, [target / "shared.zip"]), policy=ConflictPolicy.REJECT):
        assert (target / "shared.zip").read_bytes() == contents[0]
    await uploads.cancel_archive_upload(sessions[1].upload_id)
    assert not retained.temp_path.exists()
