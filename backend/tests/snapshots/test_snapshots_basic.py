"""Reject unsafe Restic requests before acquiring a repository writer."""

from pathlib import Path

import pytest

from app.snapshots import ResticClient


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


@pytest.mark.binary("restic")
@pytest.mark.parametrize("password", [None, "", "   "])
async def test_blank_password_opens_an_actual_unprotected_repository(tmp_path, password):
    from app.utils.exec import exec_command

    client = ResticClient(str(tmp_path / "repository"), password=password)
    await exec_command(str(client.binary_path), "init", "--insecure-no-password", env=client.env)
    assert await client.list_snapshots() == []
