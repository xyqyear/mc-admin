"""Integration tests for SnapshotService: ignores, planning, restore, staging.

Real restic against throwaway repos; server instances are fakes wired to
temp directories; dynamic config is patched per test.
"""

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.snapshots import ResticClient, SnapshotService, TargetIgnoredError
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


class FakeInstance:
    def __init__(self, project_path: Path):
        self.project_path = project_path

    def get_project_path(self) -> Path:
        return self.project_path

    def get_data_path(self) -> Path:
        return self.project_path / "data"


class FakeManager:
    def __init__(self, instances: list[FakeInstance]):
        self.instances = instances

    async def get_all_instances(self):
        return self.instances


def _make_server(servers_root: Path, server_id: str, level_name: str) -> FakeInstance:
    data = servers_root / server_id / "data"
    region = data / level_name / "region"
    region.mkdir(parents=True)
    (region / "r.0.0.mca").write_bytes(b"mca-0-0")
    (region / "r.0.1.mca").write_bytes(b"mca-0-1")
    (data / level_name / "level.dat").write_bytes(b"level")
    (data / "server.properties").write_text(f"level-name={level_name}\n")
    (data / ".mcmap" / "tiles").mkdir(parents=True)
    (data / ".mcmap" / "tiles" / "r.0.0.png").write_bytes(b"png")
    (data / "logs").mkdir()
    (data / "logs" / "latest.log").write_text("log line\n")
    (servers_root / server_id / "docker-compose.yml").write_text("services: {}\n")
    return FakeInstance(servers_root / server_id)


@contextmanager
def ignored_paths(patterns: list[str]):
    mock_config = MagicMock()
    mock_config.snapshots.ignored_paths = patterns
    with patch("app.snapshots.service.config", mock_config):
        yield


@pytest.fixture
def servers_root():
    with tempfile.TemporaryDirectory(prefix="snapshot_service_srv_") as tmp:
        yield Path(tmp)


@pytest.fixture
def repo_dir():
    with tempfile.TemporaryDirectory(prefix="snapshot_service_repo_") as tmp:
        yield Path(tmp)


@pytest.fixture
async def client(repo_dir):
    client = ResticClient(repository_path=str(repo_dir), password="svc-test")
    await exec_command(str(client.binary_path), "init", env=client.env)
    return client


@pytest.fixture
def server(servers_root):
    return _make_server(servers_root, "alpha", "my_world")


@pytest.fixture
def service(client, server):
    return SnapshotService(client, FakeManager([server]))


async def _drain(gen):
    return [ev async for ev in gen]


class TestCreateSnapshot:
    async def test_ignored_paths_excluded_from_backup(self, service, client, server):
        data = server.get_data_path()
        with ignored_paths([".mcmap", "logs"]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        assert sorted(snapshot.excludes) == [
            str(data / ".mcmap"),
            str(data / "logs"),
        ]
        nodes = await client.ls(snapshot.id, data)
        assert data / ".mcmap" not in nodes
        assert data / "logs" not in nodes
        assert data / "my_world" in nodes

    async def test_all_servers_backup_excludes_per_server(
        self, client, servers_root
    ):
        alpha = _make_server(servers_root, "alpha", "world_a")
        beta = _make_server(servers_root, "beta", "world_b")
        service = SnapshotService(client, FakeManager([alpha, beta]))

        with ignored_paths([".mcmap"]):
            snapshot = await service.create_snapshot([servers_root])

        assert sorted(snapshot.excludes) == [
            str(alpha.get_data_path() / ".mcmap"),
            str(beta.get_data_path() / ".mcmap"),
        ]

    async def test_level_name_token_expansion(self, service, client, server):
        data = server.get_data_path()
        with ignored_paths(["<LEVEL_NAME>/region"]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        assert snapshot.excludes == [str(data / "my_world" / "region")]
        nodes = await client.ls(snapshot.id, data / "my_world")
        assert data / "my_world" / "region" not in nodes
        assert data / "my_world" / "level.dat" in nodes

    async def test_snapshot_of_ignored_path_rejected(self, service, server):
        with ignored_paths([".mcmap"]):
            with pytest.raises(TargetIgnoredError):
                await service.create_snapshot(
                    [server.get_data_path() / ".mcmap"]
                )

    async def test_no_ignores_records_no_excludes(self, service, server):
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])
        assert snapshot.excludes == []


class TestRestore:
    async def test_ignored_paths_survive_inplace_restore(self, service, server):
        """The motivating bug: restore with --delete must not wipe ignored
        on-disk paths, while still reverting changes and deleting extras."""
        data = server.get_data_path()
        with ignored_paths([".mcmap", "logs"]):
            snapshot = await service.create_snapshot([server.get_project_path()])

            mca = data / "my_world" / "region" / "r.0.0.mca"
            mca.write_bytes(b"CORRUPTED")
            extraneous = data / "my_world" / "uploaded-by-accident.bin"
            extraneous.write_bytes(b"junk")
            tile = data / ".mcmap" / "tiles" / "r.0.0.png"
            tile.write_bytes(b"png-rendered-since-backup")
            log = data / "logs" / "latest.log"
            log.write_text("more logs since backup\n")

            events = await _drain(
                service.restore(snapshot.id, [server.get_project_path()])
            )

        assert mca.read_bytes() == b"mca-0-0"
        assert not extraneous.exists()
        assert tile.read_bytes() == b"png-rendered-since-backup"
        assert log.read_text() == "more logs since backup\n"

        deleted = {e.item for e in events if e.kind == "file" and e.action == "deleted"}
        assert deleted == {str(extraneous)}

    async def test_union_with_snapshot_recorded_excludes(self, service, server):
        """Config drift: paths ignored at backup time stay protected even
        after the ignore config is emptied."""
        data = server.get_data_path()
        with ignored_paths(["logs"]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        log = data / "logs" / "latest.log"
        log.write_text("written after backup\n")

        with ignored_paths([]):
            await _drain(service.restore(snapshot.id, [server.get_project_path()]))

        assert log.read_text() == "written after backup\n"

    async def test_union_with_current_config(self, service, server):
        """Reverse drift: a path that wasn't ignored at backup time but is
        ignored now survives the restore (it stays at its on-disk state)."""
        data = server.get_data_path()
        cache = data / "cache"
        cache.mkdir()
        (cache / "old.bin").write_bytes(b"old")

        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        (cache / "old.bin").write_bytes(b"new")
        (cache / "extra.bin").write_bytes(b"extra")

        with ignored_paths(["cache"]):
            await _drain(service.restore(snapshot.id, [server.get_project_path()]))

        assert (cache / "old.bin").read_bytes() == b"new"
        assert (cache / "extra.bin").read_bytes() == b"extra"

    async def test_restore_of_ignored_target_rejected(self, service, server):
        data = server.get_data_path()
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])
        with ignored_paths(["logs"]):
            with pytest.raises(TargetIgnoredError):
                await _drain(service.restore(snapshot.id, [data / "logs"]))

    async def test_single_file_restore(self, service, server):
        data = server.get_data_path()
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        properties = data / "server.properties"
        properties.write_text("level-name=changed\n")
        sibling = data / "unrelated.txt"
        sibling.write_text("untouched")

        with ignored_paths([]):
            await _drain(service.restore(snapshot.id, [properties]))

        assert properties.read_text() == "level-name=my_world\n"
        assert sibling.read_text() == "untouched"

    async def test_multi_target_progress_monotonic(self, service, server):
        data = server.get_data_path()
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        (data / "my_world" / "region" / "r.0.0.mca").write_bytes(b"X")
        (data / "server.properties").write_text("level-name=changed\n")

        targets = [data / "my_world", data / "server.properties"]
        with ignored_paths([]):
            events = await _drain(service.restore(snapshot.id, targets))

        percents = [
            e.percent_done for e in events if e.kind == "status" and e.percent_done
        ]
        assert percents == sorted(percents)
        assert all(0.0 <= p <= 1.0 for p in percents)
        assert events[-1].kind == "summary"
        assert (
            data / "my_world" / "region" / "r.0.0.mca"
        ).read_bytes() == b"mca-0-0"
        assert (data / "server.properties").read_text() == "level-name=my_world\n"

    async def test_restore_missing_target_is_noop(self, service, server):
        data = server.get_data_path()
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])
            events = await _drain(
                service.restore(snapshot.id, [data / "never-existed"])
            )
        assert [e.kind for e in events] == ["summary"]


class TestPreview:
    async def test_preview_matches_subsequent_restore(self, service, server):
        data = server.get_data_path()
        with ignored_paths([".mcmap"]):
            snapshot = await service.create_snapshot([server.get_project_path()])

            mca = data / "my_world" / "region" / "r.0.0.mca"
            mca.write_bytes(b"CHANGED")
            extraneous = data / "extra.txt"
            extraneous.write_text("x")
            (data / ".mcmap" / "tiles" / "r.0.0.png").write_bytes(b"new-tile")

            previewed = await service.preview(
                snapshot.id, [server.get_project_path()]
            )

            assert mca.read_bytes() == b"CHANGED"  # dry run did not touch disk

            preview_actions = {(e.action, e.item) for e in previewed}
            assert ("updated", str(mca)) in preview_actions
            assert ("deleted", str(extraneous)) in preview_actions
            assert not any(
                ".mcmap" in (item or "") for _, item in preview_actions
            )

            restored = await _drain(
                service.restore(snapshot.id, [server.get_project_path()])
            )
        # Exact parity: the dry run must report precisely the actions the
        # real restore performs, after applying preview's own filter
        # (unchanged dropped, zero-size restored-dir entries dropped).
        restore_actions = {
            (e.action, e.item)
            for e in restored
            if e.kind == "file"
            and (
                e.action in ("updated", "deleted")
                or (e.action == "restored" and e.size)
            )
        }
        assert preview_actions == restore_actions


class TestStage:
    async def test_stage_explicit_files_with_speculative_paths(self, service, server):
        data = server.get_data_path()
        region = data / "my_world" / "region"
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        targets = [region / "r.0.0.mca"]
        targets += [region / f"c.{i}.0.mcc" for i in range(8)]  # speculative

        with tempfile.TemporaryDirectory() as tmp:
            stage_root = Path(tmp)
            with ignored_paths([]):
                await _drain(service.stage(snapshot.id, targets, stage_root))

            staged = SnapshotService.stage_destination(
                stage_root, region / "r.0.0.mca"
            )
            assert staged.read_bytes() == b"mca-0-0"
            # Speculative paths simply don't materialize.
            assert not SnapshotService.stage_destination(
                stage_root, region / "c.0.0.mcc"
            ).exists()

    async def test_stage_directory_target(self, service, server):
        data = server.get_data_path()
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        with tempfile.TemporaryDirectory() as tmp:
            stage_root = Path(tmp)
            with ignored_paths([]):
                await _drain(
                    service.stage(snapshot.id, [data / "my_world"], stage_root)
                )
            staged_mca = SnapshotService.stage_destination(
                stage_root, data / "my_world" / "region" / "r.0.0.mca"
            )
            assert staged_mca.read_bytes() == b"mca-0-0"

    async def test_stage_never_deletes(self, service, server):
        data = server.get_data_path()
        with ignored_paths([]):
            snapshot = await service.create_snapshot([server.get_project_path()])

        with tempfile.TemporaryDirectory() as tmp:
            stage_root = Path(tmp)
            marker = stage_root / "pre-existing.txt"
            marker.write_text("keep")
            with ignored_paths([]):
                await _drain(
                    service.stage(snapshot.id, [data / "my_world"], stage_root)
                )
            assert marker.read_text() == "keep"


class TestSafetySnapshotRoundTrip:
    async def test_file_path_snapshot_restores_via_service(self, service, server):
        """Regions/chunks safety snapshots record explicit file paths; a
        rollback restores from them through the same planner."""
        data = server.get_data_path()
        region = data / "my_world" / "region"
        files = [region / "r.0.0.mca", region / "r.0.1.mca"]

        with ignored_paths([]):
            safety = await service.create_snapshot(files)

            (region / "r.0.0.mca").write_bytes(b"BROKEN")
            junk = region / "r.7.7.mca"
            junk.write_bytes(b"junk")

            await _drain(
                service.restore(safety.id, files + [junk])
            )

        assert (region / "r.0.0.mca").read_bytes() == b"mca-0-0"
        assert (region / "r.0.1.mca").read_bytes() == b"mca-0-1"
        assert not junk.exists()
