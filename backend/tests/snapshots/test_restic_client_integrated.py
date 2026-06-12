"""Integration tests for ResticClient using real restic commands.

Every test runs against a throwaway repository and temp directories.
Requires restic on PATH (CI installs the pinned version).
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.config import settings
from app.snapshots import NodeKind, ResticClient
from app.utils.exec import exec_command


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


async def _collect(gen):
    return [ev async for ev in gen]


def _tree_state(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def repo_dir():
    with tempfile.TemporaryDirectory(prefix="restic_client_repo_") as tmp:
        yield Path(tmp)


@pytest.fixture
def data_dir():
    with tempfile.TemporaryDirectory(prefix="restic_client_data_") as tmp:
        root = Path(tmp)
        (root / "world" / "region").mkdir(parents=True)
        (root / "world" / "region" / "r.0.0.mca").write_bytes(b"mca-0-0")
        (root / "world" / "region" / "r.0.1.mca").write_bytes(b"mca-0-1")
        (root / "world" / "ignored").mkdir()
        (root / "world" / "ignored" / "cache.bin").write_bytes(b"cache")
        (root / "plugins").mkdir()
        (root / "plugins" / "plug.jar").write_bytes(b"jar")
        (root / "server.properties").write_text("level-name=world\n")
        yield root


@pytest.fixture
async def client(repo_dir):
    client = ResticClient(
        repository_path=str(repo_dir), password="test-secure-password-123"
    )
    await exec_command(str(client.binary_path), "init", env=client.env)
    return client


class TestBackup:
    async def test_basic_backup_and_list(self, client, data_dir):
        snapshot = await client.backup([data_dir])

        assert len(snapshot.id) == 64
        assert len(snapshot.short_id) == 8
        assert str(data_dir) in snapshot.paths
        assert snapshot.excludes == []
        assert isinstance(snapshot.time, datetime)
        assert snapshot.summary is not None
        assert snapshot.summary.total_files_processed == 5

        snapshots = await client.list_snapshots()
        assert [s.id for s in snapshots] == [snapshot.id]

    async def test_backup_with_excludes_records_metadata(self, client, data_dir):
        exclude = str(data_dir / "world" / "ignored")
        snapshot = await client.backup([data_dir], excludes=[exclude])

        assert snapshot.excludes == [exclude]
        # Excluded content must not be in the snapshot tree.
        nodes = await client.ls(snapshot.id, data_dir / "world")
        assert data_dir / "world" / "ignored" not in nodes
        assert data_dir / "world" / "region" in nodes

        fetched = await client.get_snapshot(snapshot.id)
        assert fetched.excludes == [exclude]

    async def test_multi_path_backup(self, client, data_dir):
        snapshot = await client.backup(
            [data_dir / "world", data_dir / "plugins"]
        )
        assert sorted(snapshot.paths) == [
            str(data_dir / "plugins"),
            str(data_dir / "world"),
        ]

    async def test_backup_of_explicit_file_paths(self, client, data_dir):
        snapshot = await client.backup(
            [
                data_dir / "world" / "region" / "r.0.0.mca",
                data_dir / "world" / "region" / "r.0.1.mca",
            ]
        )
        # The tree still contains the synthesized directory hierarchy.
        nodes = await client.ls(snapshot.id, data_dir / "world" / "region")
        assert nodes[data_dir / "world" / "region" / "r.0.0.mca"] is NodeKind.FILE

    async def test_backup_rejects_relative_path(self, client):
        with pytest.raises(ValueError, match="absolute"):
            await client.backup([Path("relative/path")])

    async def test_backup_rejects_empty_paths(self, client):
        with pytest.raises(ValueError, match="At least one path"):
            await client.backup([])

    async def test_backup_empty_directory(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = await client.backup([Path(tmp)])
            assert snapshot.summary is not None
            assert snapshot.summary.total_files_processed == 0


class TestLs:
    async def test_dir_lists_self_and_one_level(self, client, data_dir):
        snapshot = await client.backup([data_dir])
        nodes = await client.ls(snapshot.id, data_dir / "world")

        assert nodes[data_dir / "world"] is NodeKind.DIR
        assert nodes[data_dir / "world" / "region"] is NodeKind.DIR
        assert nodes[data_dir / "world" / "ignored"] is NodeKind.DIR
        # One level only: grandchildren are not listed.
        assert data_dir / "world" / "region" / "r.0.0.mca" not in nodes

    async def test_file_node(self, client, data_dir):
        snapshot = await client.backup([data_dir])
        nodes = await client.ls(snapshot.id, data_dir / "server.properties")
        assert nodes == {data_dir / "server.properties": NodeKind.FILE}

    async def test_missing_path_returns_empty(self, client, data_dir):
        snapshot = await client.backup([data_dir])
        assert await client.ls(snapshot.id, data_dir / "nonexistent") == {}

    async def test_rejects_relative_path(self, client, data_dir):
        snapshot = await client.backup([data_dir])
        with pytest.raises(ValueError, match="absolute"):
            await client.ls(snapshot.id, Path("relative"))


class TestRestoreDir:
    async def test_in_place_restore_with_delete_and_exclude(self, client, data_dir):
        """The core invariant: --delete cleans extraneous files while
        excluded paths survive untouched."""
        exclude = str(data_dir / "world" / "ignored")
        snapshot = await client.backup([data_dir], excludes=[exclude])

        mca = data_dir / "world" / "region" / "r.0.0.mca"
        mca.write_bytes(b"MODIFIED")
        extraneous = data_dir / "world" / "extraneous.txt"
        extraneous.write_bytes(b"extra")
        ignored_file = data_dir / "world" / "ignored" / "cache.bin"
        ignored_file.write_bytes(b"cache-grew")

        events = await _collect(
            client.restore(
                snapshot.id,
                source_dir=data_dir,
                target_dir=data_dir,
                excludes=["/world/ignored"],
                delete=True,
            )
        )

        assert mca.read_bytes() == b"mca-0-0"
        assert not extraneous.exists()
        assert ignored_file.read_bytes() == b"cache-grew"

        file_events = [e for e in events if e.kind == "file"]
        updated = {e.item for e in file_events if e.action == "updated"}
        deleted = {e.item for e in file_events if e.action == "deleted"}
        assert str(mca) in updated
        assert str(extraneous) in deleted
        assert all(e.item is None or Path(e.item).is_absolute() for e in file_events)

        summaries = [e for e in events if e.kind == "summary"]
        assert len(summaries) == 1
        assert summaries[0].files_deleted == 1

    async def test_delete_without_exclude_removes_everything_extraneous(
        self, client, data_dir
    ):
        snapshot = await client.backup([data_dir])
        extraneous = data_dir / "world" / "extraneous.txt"
        extraneous.write_bytes(b"extra")

        await _collect(
            client.restore(
                snapshot.id, source_dir=data_dir, target_dir=data_dir, delete=True
            )
        )
        assert not extraneous.exists()

    async def test_restore_to_fresh_target(self, client, data_dir):
        snapshot = await client.backup([data_dir])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "staged"
            await _collect(
                client.restore(
                    snapshot.id, source_dir=data_dir / "world", target_dir=target
                )
            )
            assert (target / "region" / "r.0.0.mca").read_bytes() == b"mca-0-0"
            assert (target / "ignored" / "cache.bin").read_bytes() == b"cache"

    async def test_dry_run_emits_events_without_disk_mutation(self, client, data_dir):
        snapshot = await client.backup([data_dir])
        (data_dir / "world" / "region" / "r.0.0.mca").write_bytes(b"MODIFIED")
        (data_dir / "world" / "extraneous.txt").write_bytes(b"extra")
        before = _tree_state(data_dir)

        events = await _collect(
            client.restore(
                snapshot.id,
                source_dir=data_dir,
                target_dir=data_dir,
                delete=True,
                dry_run=True,
            )
        )

        assert _tree_state(data_dir) == before
        actions = {(e.action, e.item) for e in events if e.kind == "file"}
        assert ("updated", str(data_dir / "world" / "region" / "r.0.0.mca")) in actions
        assert ("deleted", str(data_dir / "world" / "extraneous.txt")) in actions

    async def test_missing_subtree_raises(self, client, data_dir):
        snapshot = await client.backup([data_dir])
        with pytest.raises(RuntimeError, match="restic restore failed"):
            await _collect(
                client.restore(
                    snapshot.id,
                    source_dir=data_dir / "nonexistent",
                    target_dir=data_dir / "nonexistent",
                )
            )


class TestRestoreFiles:
    async def test_includes_restore_only_named_files(self, client, data_dir):
        region = data_dir / "world" / "region"
        snapshot = await client.backup([data_dir])

        (region / "r.0.0.mca").write_bytes(b"MODIFIED")
        (region / "r.0.1.mca").write_bytes(b"ALSO-MODIFIED")

        await _collect(
            client.restore(
                snapshot.id,
                source_dir=region,
                target_dir=region,
                includes=["/r.0.0.mca"],
                delete=True,
            )
        )

        assert (region / "r.0.0.mca").read_bytes() == b"mca-0-0"
        # Not included → untouched even with --delete.
        assert (region / "r.0.1.mca").read_bytes() == b"ALSO-MODIFIED"

    async def test_delete_scoped_to_includes(self, client, data_dir):
        region = data_dir / "world" / "region"
        snapshot = await client.backup([data_dir])

        on_disk_only = region / "r.9.9.mca"
        on_disk_only.write_bytes(b"junk")
        sibling = region / "not-a-region.txt"
        sibling.write_bytes(b"keep me")

        await _collect(
            client.restore(
                snapshot.id,
                source_dir=region,
                target_dir=region,
                includes=["/r.0.0.mca", "/r.9.9.mca"],
                delete=True,
            )
        )

        assert not on_disk_only.exists()
        assert sibling.read_bytes() == b"keep me"

    async def test_speculative_includes_are_noops(self, client, data_dir):
        region = data_dir / "world" / "region"
        snapshot = await client.backup([data_dir])
        before = _tree_state(data_dir)

        await _collect(
            client.restore(
                snapshot.id,
                source_dir=region,
                target_dir=region,
                includes=[f"/c.{i}.0.mcc" for i in range(64)],
                delete=True,
            )
        )
        assert _tree_state(data_dir) == before

    async def test_restore_from_file_path_snapshot_via_parent(self, client, data_dir):
        """Safety snapshots record explicit file paths; the synthesized tree
        still allows parent-subtree restores."""
        region = data_dir / "world" / "region"
        snapshot = await client.backup(
            [region / "r.0.0.mca", region / "r.0.1.mca"]
        )

        (region / "r.0.0.mca").write_bytes(b"MODIFIED")
        junk = region / "r.5.5.mca"
        junk.write_bytes(b"junk")

        await _collect(
            client.restore(
                snapshot.id,
                source_dir=region,
                target_dir=region,
                includes=["/r.0.0.mca", "/r.5.5.mca"],
                delete=True,
            )
        )
        assert (region / "r.0.0.mca").read_bytes() == b"mca-0-0"
        assert not junk.exists()


class TestRestoreValidation:
    async def test_excludes_and_includes_forbidden(self, client, data_dir):
        with pytest.raises(ValueError, match="forbids"):
            await _collect(
                client.restore(
                    "any",
                    source_dir=data_dir,
                    target_dir=data_dir,
                    excludes=["/a"],
                    includes=["/b"],
                )
            )

    async def test_relative_dirs_rejected(self, client):
        with pytest.raises(ValueError, match="absolute"):
            await _collect(
                client.restore(
                    "any", source_dir=Path("rel"), target_dir=Path("/abs")
                )
            )


class TestSnapshotLifecycle:
    async def test_multiple_snapshots_chronology(self, client, data_dir):
        first = await client.backup([data_dir])
        (data_dir / "server.properties").write_text("level-name=other\n")
        second = await client.backup([data_dir])

        snapshots = await client.list_snapshots()
        by_id = {s.id: s for s in snapshots}
        assert by_id[second.id].time >= by_id[first.id].time

    async def test_forget_id_removes_snapshot(self, client, data_dir):
        first = await client.backup([data_dir])
        (data_dir / "new.txt").write_text("x")
        second = await client.backup([data_dir])

        await client.forget_id(first.id, prune=True)
        remaining = {s.id for s in await client.list_snapshots()}
        assert remaining == {second.id}

    async def test_forget_keep_last(self, client, data_dir):
        for i in range(3):
            (data_dir / "counter.txt").write_text(str(i))
            await client.backup([data_dir])

        await client.forget(keep_last=1, prune=True)
        assert len(await client.list_snapshots()) == 1

    async def test_forget_requires_policy(self, client):
        with pytest.raises(ValueError, match="retention policy"):
            await client.forget()

    async def test_get_snapshot_missing_raises(self, client, data_dir):
        await client.backup([data_dir])
        with pytest.raises(RuntimeError):
            await client.get_snapshot("ffffffff")

    async def test_locks(self, client, data_dir):
        await client.backup([data_dir])
        assert (await client.list_locks()).strip() == ""
        await client.unlock()
