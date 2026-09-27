import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.archive import uploads
from app.background_tasks import get_task_manager
from app.operations.finalization import finalize


def pending_upload(tmp_path: Path) -> uploads.ArchiveUploadSession:
    content = b'completed upload contents'
    source = tmp_path / 'input'
    source.write_bytes(content)
    archive = tmp_path / 'archive'
    archive.mkdir()
    session = uploads.ArchiveUploadSession(
        upload_id='task-upload', temp_path=source, base_path=archive,
        target_dir=archive, target_path=archive / 'test.zip', archive_path='/test.zip',
        filename='test.zip', size=len(content), allow_overwrite=False,
        created_at=uploads._now(), expires_at=uploads._new_expiry(), state='uploaded',
    )
    uploads.get_archive_upload_sessions()[session.upload_id] = session
    return session


async def test_hash_disconnect_reconnect_and_expiry_keep_the_same_input(tmp_path, monkeypatch):
    session = pending_upload(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = uploads._iter_file_sha256_events

    async def hash_file(*args):
        entered.set()
        await release.wait()
        async for event in original(*args):
            yield event

    monkeypatch.setattr(uploads, '_iter_file_sha256_events', hash_file)
    accepted = await uploads.submit_archive_hash(session.upload_id, 1)
    await asyncio.wait_for(entered.wait(), 2)
    session.expires_at = 0
    try:
        headers = await asyncio.wait_for(uploads.archive_upload_headers(session.upload_id), 1)
        assert headers['Upload-Hash-Task'] == accepted.task_id
        assert session.temp_path.exists()
        repeated = await uploads.submit_archive_hash(session.upload_id, 1)
        assert repeated == accepted
    finally:
        release.set()
    future = get_task_manager().get_future(accepted.task_id)
    assert future is not None
    result = await asyncio.wait_for(future, 2)
    assert result.success and result.data
    assert result.data['sha256'] == hashlib.sha256(session.temp_path.read_bytes()).hexdigest()
    assert session.state == 'hashed' and not session.target_path.exists()


async def test_cancel_waits_for_hash_cleanup_before_removing_input(tmp_path, monkeypatch):
    session = pending_upload(tmp_path)
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hash_file(*args):
        try:
            entered.set()
            await asyncio.Event().wait()
            yield uploads.ArchiveSHA256Event(event_type='progress')
        finally:
            cleaning.set()
            await finalize(release.wait())
            assert session.temp_path.exists()

    monkeypatch.setattr(uploads, '_iter_file_sha256_events', hash_file)
    accepted = await uploads.submit_archive_hash(session.upload_id, 1)
    await asyncio.wait_for(entered.wait(), 2)
    cancel = asyncio.create_task(uploads.cancel_archive_upload(session.upload_id))
    await asyncio.wait_for(cleaning.wait(), 2)
    assert not cancel.done() and session.temp_path.exists()
    release.set()
    await asyncio.wait_for(cancel, 2)
    assert not session.temp_path.exists()
    task = get_task_manager().get_task(accepted.task_id)
    assert task is not None and task.status.value == 'cancelled'


async def test_publication_retains_association_and_rejects_cancel_during_copy(tmp_path, monkeypatch):
    session = pending_upload(tmp_path)
    async for _ in uploads.iter_archive_upload_sha256_events(session.upload_id):
        pass
    digest = session.server_sha256
    assert digest
    request = uploads.ArchiveUploadVerifyRequest(sha256=digest)
    entered, release = asyncio.Event(), asyncio.Event()
    original = uploads.async_fs.copy2

    async def copy(source, destination):
        entered.set()
        await release.wait()
        await original(source, destination)

    monkeypatch.setattr(uploads.async_fs, 'copy2', copy)
    accepted = await uploads.submit_archive_publication(session.upload_id, request, 1)
    await asyncio.wait_for(entered.wait(), 2)
    try:
        assert await asyncio.wait_for(uploads.submit_archive_publication(session.upload_id, request, 1), 1) == accepted
        with pytest.raises(HTTPException) as error:
            await uploads.cancel_archive_upload(session.upload_id)
        assert error.value.status_code == 423
        assert session.temp_path.exists()
    finally:
        release.set()
    future = get_task_manager().get_future(accepted.task_id)
    assert future is not None
    result = await asyncio.wait_for(future, 2)
    assert result.success
    assert hashlib.sha256(session.target_path.read_bytes()).hexdigest() == digest
    assert await uploads.submit_archive_publication(session.upload_id, request, 1) == accepted
    headers = await uploads.archive_upload_headers(session.upload_id)
    assert headers['Upload-State'] == 'published' and headers['Upload-Publish-Task'] == accepted.task_id
    assert not session.temp_path.exists()
