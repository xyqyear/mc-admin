import asyncio
from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.files import base
from app.files.api_models import DownloadManifestRequest
from app.files.downloads import download_manifest
from app.operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from app.servers.references import ServerRef
from tests.files.test_application_ownership import file_application

__all__ = ["file_application"]


def reference(env):
    return ServerRef("first", 1, env.runtime.settings.server_path, env.instance.get_project_path(), env.data)


async def test_manifest_pages_preserve_selected_tree_empty_directories_and_literal_names(file_application):
    env = file_application
    (env.data / "chosen" / "empty").mkdir(parents=True)
    (env.data / "chosen" / "same.txt").write_bytes(b"first")
    (env.data / "chosen" / "nested").mkdir()
    (env.data / "chosen" / "nested" / "same.txt").write_bytes(b"second")
    (env.data / "chosen" / "config\\notes.txt").write_bytes(b"literal")
    cursor = None
    entries = []
    for _ in range(10):
        page = await download_manifest(reference(env), DownloadManifestRequest(paths=["/chosen", "chosen/nested/same.txt", "chosen"], cursor=cursor, limit=2))
        assert not page.errors
        assert len(page.entries) <= 2
        assert page.server_generation == 1
        entries.extend((entry.path, entry.type, entry.size) for entry in page.entries)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert cursor is None
    assert len(entries) == len(set(entries)) == 6
    assert set(entries) == {
        ("chosen", "directory", 0), ("chosen/empty", "directory", 0),
        ("chosen/nested", "directory", 0), ("chosen/same.txt", "file", 5),
        ("chosen/nested/same.txt", "file", 6), ("chosen/config\\notes.txt", "file", 7),
    }


async def test_manifest_confines_links_and_reports_unsupported_recursive_aliases(file_application):
    env = file_application
    (env.data / "export").mkdir()
    (env.data / "export" / "file-link").symlink_to(env.data / "plugin.conf")
    (env.data / "export" / "directory-link").symlink_to(env.data / "world", target_is_directory=True)
    (env.data / "export" / "escape").symlink_to(env.instance.get_project_path())
    page = await download_manifest(reference(env), DownloadManifestRequest(paths=["export"]))
    assert {(entry.path, entry.size) for entry in page.entries if entry.type == "file"} == {("export/file-link", len(b"plugin-original"))}
    assert {error.path for error in page.errors} == {"export/directory-link", "export/escape"}
    assert not any(entry.path.startswith("export/directory-link/") for entry in page.entries)
    for escaping in ("../docker-compose.yml", "export/escape"):
        with pytest.raises(HTTPException) as error:
            await download_manifest(reference(env), DownloadManifestRequest(paths=[escaping]))
        assert error.value.status_code == 400


async def test_manifest_cursor_binds_scope_generation_and_directory_structure(file_application):
    env = file_application
    page = await download_manifest(reference(env), DownloadManifestRequest(paths=["world"], limit=1))
    assert page.next_cursor is not None
    for changed_ref, changed_paths in ((replace(reference(env), generation=2), ["world"]), (reference(env), ["plugin.conf"])):
        with pytest.raises(HTTPException) as error:
            await download_manifest(changed_ref, DownloadManifestRequest(paths=changed_paths, cursor=page.next_cursor))
        assert error.value.status_code == 409
    (env.data / "world" / "new.dat").write_bytes(b"new")
    with pytest.raises(HTTPException) as error:
        await download_manifest(reference(env), DownloadManifestRequest(paths=["world"], cursor=page.next_cursor))
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await download_manifest(reference(env), DownloadManifestRequest(paths=["world"], cursor="invalid"))
    assert error.value.status_code == 400


@pytest.mark.parametrize("invalid", ["/", "world/..", "../docker-compose.yml", "missing"])
async def test_batch_delete_preflights_all_targets_without_touching_valid_files(file_application, invalid):
    env = file_application
    with pytest.raises(HTTPException):
        await env.application.submit_delete_batch(["plugin.conf", invalid])
    assert (env.data / "plugin.conf").read_bytes() == b"plugin-original"
    assert (env.data / "world" / "level.dat").read_bytes() == b"world-original"
    assert not await env.journal.list()


async def test_batch_delete_owns_all_scopes_and_deduplicates_parent_targets(file_application):
    env = file_application
    async with get_operation_coordinator().acquire([ResourceClaim(ResourceKind.FILES, "first", "data/world")]):
        with pytest.raises(HTTPException) as error:
            await env.application.submit_delete_batch(["plugin.conf", "world"])
        assert error.value.status_code == 423
        assert (env.data / "plugin.conf").exists()
        assert not await env.journal.list()
    accepted = await env.application.submit_delete_batch(["world/level.dat", "/world", "plugin.conf", "plugin.conf"])
    terminal = await asyncio.wait_for(env.tasks.get_future(accepted.task_id), 5)
    assert terminal.success
    assert terminal.data is not None
    assert terminal.data["deleted"] == 2 and terminal.data["failed"] == 0
    assert terminal.data["paths"] == ["plugin.conf", "world"]
    assert not (env.data / "world").exists()
    assert not (env.data / "plugin.conf").exists()
    assert (env.data / "server.properties").exists()


async def test_batch_delete_retains_partial_failures_and_continues_unrelated_targets(file_application, monkeypatch):
    env = file_application
    original = base.delete_file_or_directory

    async def fail_one(root, path):
        if path == "plugin.conf":
            raise PermissionError("private adapter detail")
        return await original(root, path)

    monkeypatch.setattr(base, "delete_file_or_directory", fail_one)
    accepted = await env.application.submit_delete_batch(["plugin.conf", "world"])
    terminal = await asyncio.wait_for(env.tasks.get_future(accepted.task_id), 5)
    assert not terminal.success
    detail = await env.tasks.get_task_detail(accepted.task_id)
    assert detail is not None and detail.result is not None
    assert detail.result["failed"] == 1 and detail.result["deleted"] == 1
    assert {entry["path"]: entry["status"] for entry in detail.result["results"]} == {"plugin.conf": "failed", "world": "deleted"}
    assert (env.data / "plugin.conf").exists()
    assert not (env.data / "world").exists()
    assert "private adapter" not in str(detail.result)
    assert (await env.journal.get_task_result(accepted.task_id)) == detail.result


async def test_batch_delete_cancellation_finishes_current_target_and_retains_pending_results(file_application, monkeypatch):
    env = file_application
    entered, release = asyncio.Event(), asyncio.Event()
    original = base.delete_file_or_directory

    async def controlled(root, path):
        await original(root, path)
        entered.set()
        await release.wait()
        return "done"

    monkeypatch.setattr(base, "delete_file_or_directory", controlled)
    accepted = await env.application.submit_delete_batch(["plugin.conf", "world"])
    await asyncio.wait_for(entered.wait(), 5)
    cancelling = asyncio.create_task(env.tasks.cancel(accepted.task_id))
    await asyncio.sleep(0)
    assert get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.FILES, "first", "data/plugin.conf"))
    release.set()
    await asyncio.wait_for(cancelling, 5)
    terminal = await asyncio.wait_for(env.tasks.get_future(accepted.task_id), 5)
    assert not terminal.success
    saved = await env.journal.get_task_result(accepted.task_id)
    assert saved is not None
    assert saved["deleted"] == 1 and saved["pending"] == 1
    detail = await env.tasks.get_task_detail(accepted.task_id)
    assert detail is not None and detail.result == saved
    assert not (env.data / "plugin.conf").exists()
    assert (env.data / "world" / "level.dat").exists()
    assert not get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.FILES, "first", "data/plugin.conf"))


async def test_batch_delete_cancelled_before_start_retains_all_pending_targets(file_application):
    env = file_application
    accepted = await env.application.submit_delete_batch(["plugin.conf", "world"])
    await env.tasks.cancel(accepted.task_id)
    terminal = await asyncio.wait_for(env.tasks.get_future(accepted.task_id), 5)
    assert not terminal.success
    detail = await env.tasks.get_task_detail(accepted.task_id)
    assert detail is not None and detail.result is not None
    assert detail.result["deleted"] == 0 and detail.result["pending"] == 2
    assert (env.data / "plugin.conf").exists()
    assert (env.data / "world").exists()
