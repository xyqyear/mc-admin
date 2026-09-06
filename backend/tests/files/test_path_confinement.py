from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from app.files.base import (
    create_file_or_directory,
    delete_file_or_directory,
    get_file_content,
    get_file_items,
    rename_file_or_directory,
    update_file_content,
)
from app.files.multi_file import (
    check_upload_conflicts,
    set_upload_policy,
    upload_multiple_files,
)
from app.files.types import (
    CreateFileRequest,
    FileStructureItem,
    MultiFileUploadRequest,
    OverwritePolicy,
    RenameFileRequest,
)


@pytest.mark.parametrize("path", ["../outside.txt", "/../outside.txt", "link/outside.txt"])
async def test_file_operations_cannot_escape(tmp_path: Path, path: str):
    base = tmp_path / "data"
    base.mkdir()
    (tmp_path / "outside.txt").write_text("untouched")
    (base / "link").symlink_to(tmp_path, target_is_directory=True)
    for action in (
        lambda: get_file_content(base, path),
        lambda: update_file_content(base, path, "changed"),
        lambda: delete_file_or_directory(base, path),
        lambda: rename_file_or_directory(
            base, RenameFileRequest(old_path=path, new_name="renamed.txt")
        ),
    ):
        with pytest.raises(HTTPException) as error:
            await action()
        assert error.value.status_code == 400
    assert (tmp_path / "outside.txt").read_text() == "untouched"


async def test_listing_creation_and_root_mutation_are_confined(tmp_path: Path):
    base = tmp_path / "data"
    base.mkdir()
    (base / "safe.txt").write_text("safe")
    for action in (
        lambda: get_file_items(base, ".."),
        lambda: create_file_or_directory(
            base, CreateFileRequest(name="new.txt", path="..", type="file")
        ),
        lambda: create_file_or_directory(
            base, CreateFileRequest(name="../new.txt", path="/", type="file")
        ),
        lambda: rename_file_or_directory(
            base, RenameFileRequest(old_path="safe.txt", new_name="../new.txt")
        ),
        lambda: delete_file_or_directory(base, "/"),
        lambda: rename_file_or_directory(
            base, RenameFileRequest(old_path="/", new_name="moved")
        ),
    ):
        with pytest.raises(HTTPException) as error:
            await action()
        assert error.value.status_code == 400
    assert (base / "safe.txt").read_text() == "safe"


async def test_multipart_rejects_escape_before_writing_any_file(tmp_path: Path):
    base = tmp_path / "data"
    base.mkdir()
    with pytest.raises(HTTPException) as error:
        await check_upload_conflicts(
            base,
            "/",
            MultiFileUploadRequest(
                files=[FileStructureItem(path="../outside.txt", name="outside.txt", type="file")]
            ),
        )
    assert error.value.status_code == 400
    session = await check_upload_conflicts(base, "/", MultiFileUploadRequest(files=[]))
    await set_upload_policy(session.session_id, OverwritePolicy(mode="always_overwrite"))
    with pytest.raises(HTTPException) as error:
        await upload_multiple_files(
            base,
            session.session_id,
            "/",
            [
                UploadFile(filename="safe.txt", file=BytesIO(b"safe")),
                UploadFile(filename="../outside.txt", file=BytesIO(b"escape")),
            ],
        )
    assert error.value.status_code == 400
    assert not (base / "safe.txt").exists()
    assert not (tmp_path / "outside.txt").exists()


async def test_rename_preserves_internal_symlink_target(tmp_path: Path):
    (tmp_path / "original.txt").write_text("preserved")
    (tmp_path / "link.txt").symlink_to("original.txt")
    await rename_file_or_directory(
        tmp_path, RenameFileRequest(old_path="link.txt", new_name="renamed.txt")
    )
    assert (tmp_path / "original.txt").read_text() == "preserved"
    assert (tmp_path / "renamed.txt").is_symlink()
    assert not (tmp_path / "link.txt").exists()


async def test_backslash_is_a_literal_linux_filename_character(tmp_path: Path):
    original_name = r"config\notes.txt"
    renamed_name = r"config\renamed.txt"
    await create_file_or_directory(
        tmp_path, CreateFileRequest(name=original_name, path="/", type="file")
    )
    await update_file_content(tmp_path, original_name, "preserved")
    await rename_file_or_directory(
        tmp_path, RenameFileRequest(old_path=original_name, new_name=renamed_name)
    )
    assert await get_file_content(tmp_path, renamed_name) == "preserved"
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / original_name).exists()
    await delete_file_or_directory(tmp_path, renamed_name)
    assert not (tmp_path / renamed_name).exists()
