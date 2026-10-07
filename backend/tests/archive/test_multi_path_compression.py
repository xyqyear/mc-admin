import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.archive import application as archives
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
    plan = await prepare_compression(
        env.instance, None, paths=["a", "a/same.txt", "b/same.txt", "a", "@selected.txt"],
        client_timestamp="20261007_154200_123",
    )
    task = await env.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "selected archive", compress(plan), server_id="first", claims=plan.claims)
    terminal = await asyncio.wait_for(task.awaitable, 10)
    assert terminal.success, terminal.error
    assert terminal.data is not None
    assert terminal.data["filename"] == "first_20261007_154200_123.7z"
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


def test_compression_accepts_browser_local_timestamp_and_legacy_requests():
    assert CreateArchiveRequest(server_id="server").client_timestamp is None
    assert CreateArchiveRequest(server_id="server", client_timestamp=None).client_timestamp is None
    assert CreateArchiveRequest(server_id="server", client_timestamp="20261007_154200_123").client_timestamp == "20261007_154200_123"
    assert CreateArchiveRequest(server_id="server", client_timestamp="20240229_235959_999").client_timestamp == "20240229_235959_999"


@pytest.mark.parametrize("invalid", [
    "2026-10-07T07:42:00.123Z", "20261007_154200", "20261007_154200_1234",
    "２０２６１００７_１５４２００_１２３", "20261007_154200_123\n", "../20261007_154200_123",
    "20260229_154200_123", "20261032_154200_123", "20261307_154200_123",
    "20261007_244200_123", "20261007_156000_123", "20261007_154260_123", "00001007_154200_123",
    20261007, b"20261007_154200_123",
])
def test_compression_rejects_invalid_browser_timestamp(invalid):
    with pytest.raises(ValidationError):
        CreateArchiveRequest(server_id="server", client_timestamp=invalid)


@pytest.mark.binary("7z")
async def test_repeated_browser_timestamp_keeps_both_archive_contents(file_application):
    env = file_application
    results = []
    for content in ("first generation", "second generation"):
        (env.data / "plugin.conf").write_text(content)
        plan = await prepare_compression(
            env.instance, "/plugin.conf", client_timestamp="20261007_154200_123",
        )
        task = await env.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "same browser time", compress(plan), server_id="first", claims=plan.claims)
        terminal = await asyncio.wait_for(task.awaitable, 10)
        assert terminal.success, terminal.error
        assert terminal.data is not None
        assert not plan.stage.exists()
        results.append(terminal.data)
    assert [result["filename"] for result in results] == [
        "first_20261007_154200_123.7z", "first_20261007_154200_123 (2).7z",
    ]
    for result, content in zip(results, ("first generation", "second generation"), strict=True):
        archive = env.runtime.settings.archive_path / result["filename"]
        assert archive.stat().st_size == result["size"]
        assert await exec_command("7z", "x", "-so", str(archive), "plugin.conf") == content


@pytest.mark.binary("7z")
async def test_late_archive_collision_preserves_existing_file_and_cleans_owned_stage(file_application, monkeypatch):
    env = file_application
    plan = await prepare_compression(
        env.instance, "/plugin.conf", client_timestamp="20261007_154200_123",
    )
    original_link = archives.aioos.link

    async def publish_with_late_collision(source, destination):
        assert source == plan.stage and destination == plan.output
        assert source.is_file()
        destination.write_bytes(b"existing archive must remain intact")
        await original_link(source, destination)

    monkeypatch.setattr(archives.aioos, "link", publish_with_late_collision)
    task = await env.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "late collision", compress(plan), server_id="first", claims=plan.claims)
    terminal = await asyncio.wait_for(task.awaitable, 10)
    assert not terminal.success
    assert terminal.error is not None
    assert "同名压缩包已存在" in terminal.error
    assert plan.output.read_bytes() == b"existing archive must remain intact"
    assert not plan.stage.exists()
    assert (env.data / "plugin.conf").read_bytes() == b"plugin-original"
