"""Unit tests for ignore-path resolution and restic pattern translation."""

from pathlib import Path

import pytest

from app.minecraft.properties import (
    DEFAULT_LEVEL_NAME,
    read_level_name,
    read_level_name_sync,
)
from app.snapshots.ignores import (
    backup_excludes,
    is_ignored,
    resolve_all_ignores,
    resolve_server_ignores,
    subtree_excludes,
)


def _write_properties(data_path: Path, level_name: str | None) -> None:
    data_path.mkdir(parents=True, exist_ok=True)
    lines = ["#Minecraft server properties", "server-port=25565"]
    if level_name is not None:
        lines.append(f"level-name={level_name}")
    (data_path / "server.properties").write_text("\n".join(lines) + "\n")


class TestReadLevelName:
    def test_reads_level_name(self, tmp_path):
        _write_properties(tmp_path, "my_world")
        assert read_level_name_sync(tmp_path) == "my_world"

    def test_missing_properties_file(self, tmp_path):
        assert read_level_name_sync(tmp_path) == DEFAULT_LEVEL_NAME

    def test_missing_level_name_entry(self, tmp_path):
        _write_properties(tmp_path, None)
        assert read_level_name_sync(tmp_path) == DEFAULT_LEVEL_NAME

    def test_blank_level_name(self, tmp_path):
        # The parser drops empty values, so a bare "level-name=" falls back.
        _write_properties(tmp_path, "")
        assert read_level_name_sync(tmp_path) == DEFAULT_LEVEL_NAME

    def test_whitespace_is_stripped(self, tmp_path):
        _write_properties(tmp_path, "  spaced  ")
        assert read_level_name_sync(tmp_path) == "spaced"

    @pytest.mark.asyncio
    async def test_async_variant(self, tmp_path):
        _write_properties(tmp_path, "async_world")
        assert await read_level_name(tmp_path) == "async_world"


class TestResolveServerIgnores:
    @pytest.mark.asyncio
    async def test_plain_paths(self, tmp_path):
        resolved = await resolve_server_ignores(tmp_path, [".mcmap", "logs/latest"])
        assert resolved == [tmp_path / ".mcmap", tmp_path / "logs/latest"]

    @pytest.mark.asyncio
    async def test_level_name_token_expansion(self, tmp_path):
        _write_properties(tmp_path, "my_world")
        resolved = await resolve_server_ignores(
            tmp_path, ["<LEVEL_NAME>/datapacks", ".mcmap"]
        )
        assert resolved == [tmp_path / "my_world/datapacks", tmp_path / ".mcmap"]

    @pytest.mark.asyncio
    async def test_token_defaults_to_world_without_properties(self, tmp_path):
        resolved = await resolve_server_ignores(tmp_path, ["<LEVEL_NAME>"])
        assert resolved == [tmp_path / "world"]

    @pytest.mark.asyncio
    async def test_token_in_nested_position(self, tmp_path):
        _write_properties(tmp_path, "overworld")
        resolved = await resolve_server_ignores(
            tmp_path, ["backups/<LEVEL_NAME>/cache"]
        )
        assert resolved == [tmp_path / "backups/overworld/cache"]

    @pytest.mark.asyncio
    async def test_properties_read_at_most_once(self, tmp_path, monkeypatch):
        _write_properties(tmp_path, "once_world")
        calls = 0

        async def counting_read(data_path):
            nonlocal calls
            calls += 1
            return "once_world"

        monkeypatch.setattr(
            "app.snapshots.ignores.read_level_name", counting_read
        )
        resolved = await resolve_server_ignores(
            tmp_path, ["<LEVEL_NAME>/a", "<LEVEL_NAME>/b", "plain"]
        )
        assert calls == 1
        assert resolved == [
            tmp_path / "once_world/a",
            tmp_path / "once_world/b",
            tmp_path / "plain",
        ]

    @pytest.mark.asyncio
    async def test_no_token_never_reads_properties(self, tmp_path, monkeypatch):
        async def failing_read(data_path):
            raise AssertionError("server.properties should not be read")

        monkeypatch.setattr(
            "app.snapshots.ignores.read_level_name", failing_read
        )
        resolved = await resolve_server_ignores(tmp_path, [".mcmap"])
        assert resolved == [tmp_path / ".mcmap"]


class _FakeInstance:
    def __init__(self, data_path: Path):
        self._data_path = data_path

    def get_data_path(self) -> Path:
        return self._data_path


class _FakeManager:
    def __init__(self, instances):
        self._instances = instances

    async def get_all_instances(self):
        return self._instances


class TestResolveAllIgnores:
    @pytest.mark.asyncio
    async def test_across_instances(self, tmp_path):
        data_a = tmp_path / "a" / "data"
        data_b = tmp_path / "b" / "data"
        _write_properties(data_a, "world_a")
        _write_properties(data_b, "world_b")
        manager = _FakeManager([_FakeInstance(data_a), _FakeInstance(data_b)])

        resolved = await resolve_all_ignores(manager, ["<LEVEL_NAME>/x", ".mcmap"])
        assert resolved == [
            data_a / "world_a/x",
            data_a / ".mcmap",
            data_b / "world_b/x",
            data_b / ".mcmap",
        ]

    @pytest.mark.asyncio
    async def test_empty_patterns_skip_instance_enumeration(self):
        class ExplodingManager:
            async def get_all_instances(self):
                raise AssertionError("should not be called")

        assert await resolve_all_ignores(ExplodingManager(), []) == []


class TestIsIgnored:
    def test_exact_match(self):
        assert is_ignored(Path("/srv/data/.mcmap"), [Path("/srv/data/.mcmap")])

    def test_descendant(self):
        assert is_ignored(
            Path("/srv/data/.mcmap/tiles/r.0.0.png"), [Path("/srv/data/.mcmap")]
        )

    def test_sibling_prefix_no_match(self):
        assert not is_ignored(
            Path("/srv/data/.mcmapx"), [Path("/srv/data/.mcmap")]
        )

    def test_unrelated(self):
        assert not is_ignored(Path("/srv/data/world"), [Path("/srv/data/.mcmap")])

    def test_empty_ignores(self):
        assert not is_ignored(Path("/srv/data"), [])


class TestSubtreeExcludes:
    def test_ignore_under_root(self):
        patterns = subtree_excludes(
            Path("/srv/x/data"), [Path("/srv/x/data/world/ignored")]
        )
        assert patterns == ["/world/ignored"]

    def test_ignore_equal_to_root_excluded(self):
        assert subtree_excludes(Path("/srv/x/data"), [Path("/srv/x/data")]) == []

    def test_ignore_outside_root_dropped(self):
        assert (
            subtree_excludes(Path("/srv/x/data"), [Path("/srv/y/data/.mcmap")]) == []
        )

    def test_mixed(self):
        patterns = subtree_excludes(
            Path("/srv/x"),
            [
                Path("/srv/x/data/.mcmap"),
                Path("/srv/y/data/.mcmap"),
                Path("/srv/x/data/logs"),
            ],
        )
        assert patterns == ["/data/.mcmap", "/data/logs"]


class TestBackupExcludes:
    def test_under_backup_path(self):
        excludes = backup_excludes(
            [Path("/srv/x")], [Path("/srv/x/data/.mcmap"), Path("/srv/y/data/.mcmap")]
        )
        assert excludes == ["/srv/x/data/.mcmap"]

    def test_all_servers_root(self):
        excludes = backup_excludes(
            [Path("/srv")], [Path("/srv/x/data/.mcmap"), Path("/srv/y/data/.mcmap")]
        )
        assert excludes == ["/srv/x/data/.mcmap", "/srv/y/data/.mcmap"]

    def test_outside_backup_paths(self):
        assert backup_excludes([Path("/other")], [Path("/srv/x/data/.mcmap")]) == []
