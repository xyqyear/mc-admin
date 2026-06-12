"""Unit tests for ResticClient construction, validation, and models."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import ResticSettings
from app.snapshots import ResticClient, ResticRestoreEvent, ResticSnapshot


class TestResticClientConstruction:
    def test_initialization(self):
        client = ResticClient(
            repository_path="/test/repo/path", password="test-password"
        )

        assert client.repository_path == "/test/repo/path"
        assert client.use_password is True
        assert client.env["RESTIC_REPOSITORY"] == "/test/repo/path"
        assert client.env["RESTIC_PASSWORD"] == "test-password"

    def test_binary_path(self):
        client = ResticClient(
            repository_path="/test/repo/path",
            password="test-password",
            binary_path="/custom/bin/restic",
        )

        assert client.binary_path == Path("/custom/bin/restic")
        assert client._build_args("version") == ["/custom/bin/restic", "version"]

    @pytest.mark.parametrize("password", [None, "", "   "])
    def test_no_password_modes(self, password):
        client = ResticClient(repository_path="/test/repo", password=password)

        assert client.use_password is False
        assert "RESTIC_PASSWORD" not in client.env
        assert client._build_args("snapshots")[-1] == "--insecure-no-password"

    def test_password_mode_omits_insecure_flag(self):
        client = ResticClient(repository_path="/test/repo", password="secret")
        assert "--insecure-no-password" not in client._build_args("snapshots")


class TestValidation:
    async def test_backup_requires_absolute_path(self):
        client = ResticClient("/test/repo", "password")
        with pytest.raises(ValueError, match="Path must be absolute"):
            await client.backup([Path("relative/path")])

    async def test_backup_requires_non_empty_paths(self):
        client = ResticClient("/test/repo", "password")
        with pytest.raises(ValueError, match="At least one path"):
            await client.backup([])

    async def test_restore_forbids_includes_with_excludes(self):
        client = ResticClient("/test/repo", "password")
        with pytest.raises(ValueError, match="forbids"):
            async for _ in client.restore(
                "snap",
                source_dir=Path("/a"),
                target_dir=Path("/a"),
                excludes=["/x"],
                includes=["/y"],
            ):
                pass

    async def test_restore_requires_absolute_dirs(self):
        client = ResticClient("/test/repo", "password")
        with pytest.raises(ValueError, match="absolute"):
            async for _ in client.restore(
                "snap", source_dir=Path("rel"), target_dir=Path("/abs")
            ):
                pass

    async def test_ls_requires_absolute_path(self):
        client = ResticClient("/test/repo", "password")
        with pytest.raises(ValueError, match="absolute"):
            await client.ls("snap", Path("relative"))

    async def test_forget_requires_policy(self):
        client = ResticClient("/test/repo", "password")

        with pytest.raises(
            ValueError,
            match="At least one retention policy parameter must be specified",
        ):
            await client.forget()

        with pytest.raises(ValueError):
            await client.forget(keep_tag=[])

        with pytest.raises(ValueError):
            await client.forget(keep_within="   ")


class TestModels:
    def test_restic_snapshot_model(self):
        snapshot = ResticSnapshot(
            time=datetime.now(timezone.utc),
            paths=["/test/path1", "/test/path2"],
            hostname="test-host",
            username="test-user",
            program_version="restic 0.18.1",
            id="abc123def456",
            short_id="abc123",
        )

        assert snapshot.excludes == []
        assert snapshot.hostname == "test-host"
        assert len(snapshot.paths) == 2

    def test_restic_snapshot_model_with_excludes(self):
        snapshot = ResticSnapshot(
            time=datetime.now(timezone.utc),
            paths=["/srv/x"],
            excludes=["/srv/x/data/.mcmap"],
            hostname="h",
            username="u",
            id="i" * 64,
            short_id="i" * 8,
        )
        assert snapshot.excludes == ["/srv/x/data/.mcmap"]

    def test_restore_event_model(self):
        event = ResticRestoreEvent(
            kind="file", action="updated", item="/test/file.txt", size=1024
        )
        assert event.kind == "file"
        assert event.action == "updated"
        assert event.item == "/test/file.txt"
        assert event.size == 1024


class TestConfigurationIntegration:
    def test_restic_settings_validation(self):
        settings = ResticSettings(
            repository_path="/backup/repo", password="strong-password"
        )

        assert settings.repository_path == "/backup/repo"
        assert settings.password == "strong-password"
