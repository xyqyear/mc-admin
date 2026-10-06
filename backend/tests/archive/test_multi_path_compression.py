import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.archive.api_models import CreateArchiveRequest
from app.archive.application import compress, prepare_compression
from app.background_tasks import TaskType
from app.utils.exec import exec_command
from tests.files.test_application_ownership import file_application

__all__ = ["file_application"]


@pytest.mark.binary("7z")
async def test_multi_path_archive_preserves_original_paths_empty_directories_and_literal_names(file_application):
    env = file_application
    (env.data / "a" / "empty").mkdir(parents=True)
    (env.data / "b").mkdir()
    (env.data / "a" / "same.txt").write_text("first content")
    (env.data / "b" / "same.txt").write_text("second content")
    (env.data / "a" / "@literal[1].txt").write_text("literal filename")
    (env.data / "@selected.txt").write_text("literal root")
    (env.data / "a" / "unselected-parent-sibling.txt").write_text("selected with a")
    plan = await prepare_compression(env.instance, None, paths=["a", "a/same.txt", "b/same.txt", "a", "@selected.txt"])
    task = await env.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "selected archive", compress(plan), server_id="first", claims=plan.claims)
    terminal = await asyncio.wait_for(task.awaitable, 10)
    assert terminal.success, terminal.error
    assert plan.output.is_file() and not plan.stage.exists()
    listing = await exec_command("7z", "l", "-slt", str(plan.output))
    members = [line.removeprefix("Path = ") for line in listing.split("----------\n", 1)[1].splitlines() if line.startswith("Path = ")]
    assert set(members) == {"a", "a/empty", "a/same.txt", "a/@literal[1].txt", "a/unselected-parent-sibling.txt", "b/same.txt", "@selected.txt"}
    assert len(members) == 7
    assert await exec_command("7z", "x", "-so", "-spd", str(plan.output), "a/same.txt") == "first content"
    assert await exec_command("7z", "x", "-so", "-spd", str(plan.output), "b/same.txt") == "second content"
    assert await exec_command("7z", "x", "-so", "-spd", str(plan.output), "a/@literal[1].txt") == "literal filename"
    assert (env.data / "plugin.conf").read_text() == "plugin-original"


@pytest.mark.parametrize("invalid", ["../docker-compose.yml", "missing"])
async def test_multi_path_compression_rejects_invalid_complete_scope_before_stage(file_application, invalid):
    env = file_application
    with pytest.raises(HTTPException):
        await prepare_compression(env.instance, None, paths=["plugin.conf", invalid])
    assert not list(env.runtime.settings.archive_path.iterdir())
    assert (env.data / "plugin.conf").read_bytes() == b"plugin-original"
    assert not await env.journal.list()


@pytest.mark.binary("7z")
async def test_multi_path_archive_keeps_symlinks_without_reading_external_targets(file_application):
    env = file_application
    external = env.instance.get_project_path() / "external-secret.txt"
    external.write_text("outside contents must remain outside")
    (env.data / "links").mkdir()
    (env.data / "links" / "external").symlink_to(external)
    plan = await prepare_compression(env.instance, None, paths=["links"])
    task = await env.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "links archive", compress(plan), server_id="first", claims=plan.claims)
    terminal = await asyncio.wait_for(task.awaitable, 10)
    assert terminal.success, terminal.error
    content = await exec_command("7z", "x", "-so", str(plan.output), "links/external")
    assert "outside contents must remain outside" not in content
    assert content == str(external)


@pytest.mark.binary("7z")
async def test_many_selected_paths_survive_argument_batches_without_scope_expansion(file_application):
    env = file_application
    paths = [f"selected-{index:04d}-" + "x" * 160 + ".txt" for index in range(210)]
    for index, path in enumerate(paths):
        (env.data / path).write_text(f"selected content {index}")
    plan = await prepare_compression(env.instance, None, paths=paths)
    task = await env.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "many selected files", compress(plan), server_id="first", claims=plan.claims)
    terminal = await asyncio.wait_for(task.awaitable, 10)
    assert terminal.success, terminal.error
    listing = await exec_command("7z", "l", "-slt", str(plan.output))
    members = [line.removeprefix("Path = ") for line in listing.split("----------\n", 1)[1].splitlines() if line.startswith("Path = ")]
    assert set(members) == set(paths)
    assert len(members) == len(paths)
    assert await exec_command("7z", "x", "-so", str(plan.output), paths[-1]) == "selected content 209"


@pytest.mark.binary("7z")
async def test_batch_root_archive_uses_data_relative_members(file_application):
    env = file_application
    (env.data / "empty").mkdir()
    plan = await prepare_compression(env.instance, None, paths=["/"])
    task = await env.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "data root", compress(plan), server_id="first", claims=plan.claims)
    terminal = await asyncio.wait_for(task.awaitable, 10)
    assert terminal.success, terminal.error
    listing = await exec_command("7z", "l", "-slt", str(plan.output))
    members = [line.removeprefix("Path = ") for line in listing.split("----------\n", 1)[1].splitlines() if line.startswith("Path = ")]
    assert set(members) == {"empty", "world", "world/level.dat", "plugin.conf", "server.properties"}
    assert "docker-compose.yml" not in members


def test_compression_scope_accepts_legacy_and_batch_forms_without_ambiguity():
    assert CreateArchiveRequest(server_id="server", path="/plugins").paths is None
    assert CreateArchiveRequest(server_id="server", paths=["a", "b"]).path is None
    with pytest.raises(ValidationError):
        CreateArchiveRequest(server_id="server", path="/", paths=["a"])
    with pytest.raises(ValidationError):
        CreateArchiveRequest(server_id="server", paths=[])
