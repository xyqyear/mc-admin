"""Integrated tests for ResticClient against an unprotected (no-password) repo.

Mirrors the password-protected coverage in test_restic_client_integrated.py
for the --insecure-no-password code path.
"""

import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from app.config import settings
from app.snapshots import ResticClient
from app.utils.exec import exec_command


async def _drain(gen):
    summary = None
    async for ev in gen:
        if ev.kind == "summary":
            summary = ev
    return summary


def check_restic_available():
    try:
        result = subprocess.run(
            [str(settings.restic_binary_path), "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(
    not check_restic_available(),
    reason="restic command not available - install restic to run these tests",
)


class TestResticClientNoPasswordIntegrated:
    @pytest.fixture
    def repo_dir(self):
        with tempfile.TemporaryDirectory(prefix="restic_test_repo_nopass_") as tmp:
            yield Path(tmp)

    @pytest.fixture
    def backup_dir(self):
        with tempfile.TemporaryDirectory(prefix="restic_test_backup_nopass_") as tmp:
            backup_dir = Path(tmp)
            (backup_dir / "test_file1.txt").write_text(
                "Original content of file 1\nSecond line"
            )
            (backup_dir / "test_file2.txt").write_text(
                "Original content of file 2\nAnother line"
            )
            subdir = backup_dir / "nested_dir"
            subdir.mkdir()
            (subdir / "nested_file.txt").write_text("Nested file original content")
            yield backup_dir

    @pytest.fixture
    async def client(self, repo_dir):
        client = ResticClient(repository_path=str(repo_dir), password=None)
        await exec_command(
            str(client.binary_path),
            "init",
            "--insecure-no-password",
            env=client.env,
        )
        return client

    async def test_backup_and_list(self, client, backup_dir):
        snapshot = await client.backup([backup_dir])

        assert len(snapshot.id) == 64
        assert len(snapshot.short_id) == 8
        assert str(backup_dir) in snapshot.paths
        assert isinstance(snapshot.time, datetime)

        snapshots = await client.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].id == snapshot.id

    async def test_dry_run_restore(self, client, backup_dir):
        snapshot = await client.backup([backup_dir])
        (backup_dir / "test_file1.txt").write_text("Modified for preview test")

        actions = []
        async for ev in client.restore(
            snapshot.id,
            source_dir=backup_dir,
            target_dir=backup_dir,
            delete=True,
            dry_run=True,
        ):
            if ev.kind == "file" and ev.action in ("updated", "restored", "deleted"):
                actions.append(ev)

        assert any(
            a.action == "updated" and a.item == str(backup_dir / "test_file1.txt")
            for a in actions
        )
        assert (backup_dir / "test_file1.txt").read_text() == "Modified for preview test"

    async def test_in_place_restore_with_delete(self, client, backup_dir):
        original = (backup_dir / "test_file1.txt").read_text()
        snapshot = await client.backup([backup_dir])

        (backup_dir / "test_file1.txt").write_text("Modified for restore test")
        (backup_dir / "extra_file.txt").write_text("Extra file to be deleted")

        summary = await _drain(
            client.restore(
                snapshot.id, source_dir=backup_dir, target_dir=backup_dir, delete=True
            )
        )

        assert summary is not None
        assert (backup_dir / "test_file1.txt").read_text() == original
        assert not (backup_dir / "extra_file.txt").exists()

    async def test_exclude_protection(self, client, backup_dir):
        snapshot = await client.backup(
            [backup_dir], excludes=[str(backup_dir / "nested_dir")]
        )
        nested = backup_dir / "nested_dir" / "nested_file.txt"
        nested.write_text("changed after backup")

        await _drain(
            client.restore(
                snapshot.id,
                source_dir=backup_dir,
                target_dir=backup_dir,
                excludes=["/nested_dir"],
                delete=True,
            )
        )
        assert nested.read_text() == "changed after backup"

    async def test_forget(self, client, backup_dir):
        created = []
        for i in range(3):
            (backup_dir / "test_file.txt").write_text(f"Version {i + 1}")
            created.append(await client.backup([backup_dir]))
            time.sleep(0.1)

        assert len(await client.list_snapshots()) == 3

        await client.forget(keep_last=1, prune=True)

        remaining = await client.list_snapshots()
        assert len(remaining) == 1
        assert remaining[0].id == created[-1].id

    async def test_ls(self, client, backup_dir):
        snapshot = await client.backup([backup_dir])
        nodes = await client.ls(snapshot.id, backup_dir)
        assert backup_dir / "nested_dir" in nodes
        assert backup_dir / "test_file1.txt" in nodes
