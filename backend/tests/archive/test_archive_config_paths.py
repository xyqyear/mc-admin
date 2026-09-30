import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import api_app
from tests.support.tasks import task_result


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
    monkeypatch.setitem(isolated_runtime.resources, "settings", settings)

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
