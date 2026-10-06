import asyncio
import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient

from app.config import Settings
from app.db.metadata import Base
from app.main import api_app
from app.operations.coordinator import ConflictPolicy, ResourceClaim, ResourceKind
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from tests.support.tasks import task_result


def _archive_bytes():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("marker.txt", "owned archive contents")
    return buffer.getvalue()


@pytest.mark.parametrize("directory", ["default", "relative", "absolute", "symlink"])
def test_upload_publishes_under_configured_directory(directory, tmp_path, monkeypatch, isolated_runtime):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCHIVE_PATH", raising=False)
    values = isolated_runtime.settings.model_dump(exclude={"archive_path"})
    expected = tmp_path / "archives"
    if directory == "relative":
        values["archive_path"] = "./nested/archives"
        expected = tmp_path / "nested" / "archives"
    elif directory == "absolute":
        values["archive_path"] = expected
    elif directory == "symlink":
        expected.mkdir()
        (tmp_path / "archives-link").symlink_to(expected, target_is_directory=True)
        values["archive_path"] = "archives-link"
    settings = Settings(**values)
    monkeypatch.setattr(isolated_runtime, "settings", settings)

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("pack.mcmeta", '{"pack":{"pack_format":48,"description":"AFK display"}}')
    content = buffer.getvalue()
    filename = "afk display v1.1.15 (MC 1.21-1.21.11).zip"
    digest = hashlib.sha256(content).hexdigest()

    with TestClient(api_app) as client:
        client.headers["Authorization"] = f"Bearer {settings.master_token}"
        response = client.post("/archive/upload/init", json={"filename": filename, "size": len(content)})
        assert response.status_code == 200, response.text
        upload = f"/archive/upload/{response.json()['upload_id']}"
        response = client.patch(upload, content=content, headers={"Upload-Offset": "0"})
        assert response.status_code == 200, response.text
        assert response.json()["pending_verification"]
        assert not (expected / filename).exists()
        assert task_result(client, client.post(f"{upload}/sha256"))["sha256"] == digest
        published = task_result(client, client.post(f"{upload}/verify", json={"sha256": digest}))
        assert published["path"] == f"/{filename}"
        assert (expected / filename).read_bytes() == content
        downloaded = client.get("/archive/download", params={"path": published["path"]})
        assert downloaded.status_code == 200
        assert downloaded.content == content

        outside = tmp_path / "outside"
        outside.mkdir()
        (expected / "escape").symlink_to(outside, target_is_directory=True)
        for path in ("/../outside", "/escape"):
            rejected = client.post("/archive/upload/init", json={"path": path, "filename": "escape.zip", "size": len(content)})
            assert rejected.status_code == 400, rejected.text
        assert list(outside.iterdir()) == []


def test_upload_init_rejects_a_final_target_symlink_outside_archive_root(tmp_path, isolated_runtime):
    root = isolated_runtime.settings.archive_path
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"outside bytes must remain")
    target = root / "linked.zip"
    target.symlink_to(outside)
    with TestClient(api_app) as client:
        client.headers["Authorization"] = f"Bearer {isolated_runtime.settings.master_token}"
        response = client.post("/archive/upload/init", json={
            "filename": "linked.zip", "size": len(_archive_bytes()), "allow_overwrite": True,
        })
    assert response.status_code == 400
    assert response.json()["detail"] == "Path escapes archive directory"
    assert outside.read_bytes() == b"outside bytes must remain"
    assert target.is_symlink()


def test_upload_publication_rejects_parent_retarget_after_init_and_hash(tmp_path, isolated_runtime):
    root = isolated_runtime.settings.archive_path
    incoming = root / "incoming"
    incoming.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "marker.zip").write_bytes(b"outside archive must remain")
    content = _archive_bytes()
    digest = hashlib.sha256(content).hexdigest()
    with TestClient(api_app, raise_server_exceptions=False) as client:
        client.headers["Authorization"] = f"Bearer {isolated_runtime.settings.master_token}"
        response = client.post("/archive/upload/init", json={
            "path": "/incoming", "filename": "marker.zip", "size": len(content), "allow_overwrite": True,
        })
        assert response.status_code == 200, response.text
        upload = f"/archive/upload/{response.json()['upload_id']}"
        response = client.patch(upload, content=content, headers={"Upload-Offset": "0"})
        assert response.status_code == 200
        assert task_result(client, client.post(f"{upload}/sha256"))["sha256"] == digest
        incoming.rename(root / "original-incoming")
        incoming.symlink_to(outside, target_is_directory=True)
        response = client.post(f"{upload}/verify", json={"sha256": digest})
        assert response.status_code == 400, response.text
        assert "task_id" not in response.json()
        headers = client.head(upload)
        assert headers.status_code == 204
        assert headers.headers["Upload-Publish-Task"] == ""
    assert (outside / "marker.zip").read_bytes() == b"outside archive must remain"
    assert list(outside.iterdir()) == [outside / "marker.zip"]
    assert list((root / "original-incoming").iterdir()) == []


async def test_accepted_publication_rechecks_canonical_parent_after_lease_wait(
    tmp_path, monkeypatch, isolated_runtime,
):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    runtime.task_manager.journal = journal
    root = runtime.settings.archive_path
    incoming = root / "incoming"
    incoming.mkdir()
    existing_archive = incoming / "marker.zip"
    existing_archive.write_bytes(b"original archive must remain\x00\xff")
    original = root / "original-incoming"
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker.zip"
    marker.write_bytes(b"outside archive must remain\x00\xff")
    content = _archive_bytes()
    digest = hashlib.sha256(content).hexdigest()
    coordinator = runtime.operation_coordinator
    waiting = asyncio.Event()
    original_wait = coordinator._changed.wait

    async def observe_lease_wait():
        waiting.set()
        await original_wait()

    monkeypatch.setattr(coordinator._changed, "wait", observe_lease_wait)
    headers = {"Authorization": f"Bearer {runtime.settings.master_token}"}
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test", headers=headers) as client:
        response = await client.post("/archive/upload/init", json={
            "path": "/incoming", "filename": "marker.zip", "size": len(content), "allow_overwrite": True,
        })
        assert response.status_code == 200, response.text
        upload_id = response.json()["upload_id"]
        upload = f"/archive/upload/{upload_id}"
        response = await client.patch(upload, content=content, headers={"Upload-Offset": "0"})
        assert response.status_code == 200, response.text
        assert response.json()["pending_verification"]
        response = await client.post(f"{upload}/sha256")
        assert response.status_code == 202, response.text
        hash_future = runtime.task_manager.get_future(response.json()["task_id"])
        assert hash_future is not None
        hashed = await asyncio.wait_for(asyncio.shield(hash_future), 5)
        assert hashed.success and hashed.data is not None
        assert hashed.data["sha256"] == digest
        session = runtime.archive_upload_sessions[upload_id]
        temp_path = session.temp_path
        claim = ResourceClaim(ResourceKind.ARCHIVE, path="incoming")
        try:
            async with coordinator.acquire([claim], policy=ConflictPolicy.REJECT):
                response = await client.post(f"{upload}/verify", json={"sha256": digest})
                assert response.status_code == 202, response.text
                accepted_id = response.json()["task_id"]
                await asyncio.wait_for(waiting.wait(), 5)
                task = await client.get(f"/tasks/{accepted_id}")
                assert task.status_code == 200, task.text
                assert task.json()["status"] == "running"
                assert task.json()["result"] is None
                record = await journal.get(accepted_id)
                assert record is not None and record.state is OperationState.RUNNING
                assert record.origin == "task" and record.ended_at is None
                assert {resource.path for resource in record.resources} == {
                    "incoming/marker.zip", f"incoming/.mc-admin-archive-{upload_id.replace('-', '')}.tmp",
                }
                assert temp_path.read_bytes() == content
                assert list(incoming.iterdir()) == [existing_archive]
                assert existing_archive.read_bytes() == b"original archive must remain\x00\xff"
                incoming.rename(original)
                incoming.symlink_to(outside, target_is_directory=True)

            future = runtime.task_manager.get_future(accepted_id)
            assert future is not None
            settled = await asyncio.wait_for(asyncio.shield(future), 5)
            assert not settled.success and settled.data is None
            task = await client.get(f"/tasks/{accepted_id}")
            assert task.status_code == 200, task.text
            assert task.json()["status"] == "failed"
            assert task.json()["result"] is None
            assert task.json()["error"] == "路径越界：目标路径不在文件目录内"
            persisted = await OperationJournal(runtime.database.session_factory).get(accepted_id)
            assert persisted is not None and persisted.state is OperationState.FAILED
            assert persisted.ended_at is not None and persisted.writers_stopped
            assert persisted.ownership_known and not persisted.processes
            assert not persisted.data_changed and not persisted.recovery_refs
            assert not coordinator.is_occupied(claim)
            async with coordinator.acquire([claim], policy=ConflictPolicy.REJECT):
                assert marker.read_bytes() == b"outside archive must remain\x00\xff"
            assert list(original.iterdir()) == [original / "marker.zip"]
            assert (original / "marker.zip").read_bytes() == b"original archive must remain\x00\xff"
            assert incoming.is_symlink() and incoming.resolve() == outside
            assert list(outside.iterdir()) == [marker]
            assert list(root.rglob(".mc-admin-archive-*.tmp")) == []
            assert session.state == "hashed" and temp_path.read_bytes() == content
            response = await client.delete(upload)
            assert response.status_code == 204, response.text
            assert not temp_path.exists() and upload_id not in runtime.archive_upload_sessions
        finally:
            await runtime.task_manager.shutdown()
