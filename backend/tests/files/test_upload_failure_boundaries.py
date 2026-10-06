import logging
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from app.errors import PublicOperationError
from app.files import multi_file
from app.files.types import MultiFileUploadRequest, OverwritePolicy


async def prepare_session(base: Path, *, reusable: bool = False) -> str:
    response = await multi_file.check_upload_conflicts(
        base, "/", MultiFileUploadRequest(files=[])
    )
    await multi_file.set_upload_policy(
        response.session_id, OverwritePolicy(mode="always_overwrite"), reusable=reusable
    )
    return response.session_id


@pytest.mark.parametrize("reusable", [False, True])
async def test_member_failure_keeps_partial_bytes_and_continues(tmp_path, monkeypatch, reusable):
    session_id = await prepare_session(tmp_path, reusable=reusable)
    damaged = UploadFile(filename="damaged.txt", file=BytesIO(b"partial"))
    original_read = damaged.read
    read_started = False

    async def fail_after_first_chunk(size: int = -1) -> bytes:
        nonlocal read_started
        if read_started:
            raise HTTPException(400, "adapter read failed")
        read_started = True
        return await original_read(size)

    monkeypatch.setattr(damaged, "read", fail_after_first_chunk)
    result = await multi_file.upload_multiple_files(
        tmp_path, session_id, "/",
        [damaged, UploadFile(filename="later.txt", file=BytesIO(b"complete"))],
    )
    assert result.results["damaged.txt"].status == "failed"
    assert result.results["later.txt"].model_dump() == {"status": "success", "reason": None}
    assert (tmp_path / "damaged.txt").read_bytes() == b"partial"
    assert (tmp_path / "later.txt").read_bytes() == b"complete"
    assert (multi_file.get_upload_session(session_id) is not None) is reusable


async def test_execution_path_escape_is_outer_500_and_never_writes_outside(tmp_path, monkeypatch):
    base, outside = tmp_path / "data", tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    (base / "inside").mkdir()
    alias = base / "alias"
    alias.symlink_to(base / "inside", target_is_directory=True)
    (outside / "target.txt").write_bytes(b"unchanged")
    session_id = await prepare_session(base)
    original_remove = multi_file.remove_upload_session

    def retarget_after_preflight(value: str) -> bool:
        removed = original_remove(value)
        alias.unlink()
        alias.symlink_to(outside, target_is_directory=True)
        return removed

    monkeypatch.setattr(multi_file, "remove_upload_session", retarget_after_preflight)
    with pytest.raises(HTTPException) as error:
        await multi_file.upload_multiple_files(
            base, session_id, "/",
            [UploadFile(filename="alias/target.txt", file=BytesIO(b"forbidden"))],
        )
    assert error.value.status_code == 500
    assert isinstance(error.value.detail, str)
    assert (outside / "target.txt").read_bytes() == b"unchanged"
    assert not (base / "inside" / "target.txt").exists()
    assert multi_file.get_upload_session(session_id) is None


@pytest.mark.parametrize("error_type", [RuntimeError, lambda value: HTTPException(400, value)])
async def test_parent_failure_stops_batch_and_hides_adapter_values(tmp_path, monkeypatch, caplog, error_type):
    secret = "synthetic-upload-parent-token"
    session_id = await prepare_session(tmp_path)

    async def fail_parent(*args):
        raise error_type(secret)

    monkeypatch.setattr(multi_file, "makedirs_with_ownership", fail_parent)
    with caplog.at_level(logging.ERROR), pytest.raises(HTTPException) as error:
        await multi_file.upload_multiple_files(
            tmp_path, session_id, "/",
            [UploadFile(filename="new/first.txt", file=BytesIO(b"first")),
             UploadFile(filename="later.txt", file=BytesIO(b"later"))],
        )
    assert error.value.status_code == 500
    assert isinstance(error.value.detail, str)
    assert secret not in error.value.detail + caplog.text
    assert not (tmp_path / "new").exists()
    assert not (tmp_path / "later.txt").exists()
    assert multi_file.get_upload_session(session_id) is None


@pytest.mark.parametrize("failure", ["read", "ownership"])
async def test_member_errors_hide_credentials_and_preserve_next_file(tmp_path, monkeypatch, caplog, failure):
    secret = "synthetic-upload-member-credential"
    session_id = await prepare_session(tmp_path)
    first = UploadFile(filename=f"{secret}.txt", file=BytesIO(b"written"))
    assert first.filename is not None
    if failure == "read":
        async def fail_read(size: int = -1) -> bytes:
            raise HTTPException(409, secret)

        monkeypatch.setattr(first, "read", fail_read)
    else:
        original_ownership = multi_file.set_file_ownership

        async def fail_first_ownership(target: Path, base: Path) -> None:
            if target.name == first.filename:
                raise ValueError(secret)
            await original_ownership(target, base)

        monkeypatch.setattr(multi_file, "set_file_ownership", fail_first_ownership)
    with caplog.at_level(logging.ERROR):
        result = await multi_file.upload_multiple_files(
            tmp_path, session_id, "/",
            [first, UploadFile(filename="later.txt", file=BytesIO(b"complete"))],
        )
    failed = result.results[first.filename]
    assert failed.status == "failed"
    assert failed.reason and secret not in failed.reason + result.message + caplog.text
    assert (tmp_path / first.filename).read_bytes() == (b"" if failure == "read" else b"written")
    assert (tmp_path / "later.txt").read_bytes() == b"complete"
    assert result.results["later.txt"].status == "success"


async def test_authored_safe_member_message_remains_readable(tmp_path, monkeypatch):
    session_id = await prepare_session(tmp_path)
    file = UploadFile(filename="first.txt", file=BytesIO(b"content"))

    async def fail_read(size: int = -1) -> bytes:
        raise PublicOperationError("文件暂时无法读取，请重试")

    monkeypatch.setattr(file, "read", fail_read)
    result = await multi_file.upload_multiple_files(tmp_path, session_id, "/", [file])
    assert result.results["first.txt"].model_dump() == {
        "status": "failed", "reason": "文件暂时无法读取，请重试",
    }
