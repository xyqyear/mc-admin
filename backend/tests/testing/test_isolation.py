import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import get_settings
from tests.fixtures.test_utils import OWNER_LABEL, OwnedDockerResources
from tests.support.collection import audit, matrix

BACKEND = Path(__file__).resolve().parents[2]


def run_pytest(arguments: list[str], *, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-q", *arguments],
        cwd=BACKEND, env=environment, capture_output=True, text=True, timeout=60, check=False,
    )


def test_application_defaults_are_owned(tmp_path, tmp_path_factory):
    from app.archive.uploads import ARCHIVE_UPLOAD_TMP_DIR

    root = get_settings().server_path.parent
    assert root.parent == tmp_path_factory.getbasetemp()
    assert root.name.startswith("runtime")
    assert root != tmp_path
    assert list(tmp_path.iterdir()) == []
    assert get_settings().archive_path.parent == root
    assert get_settings().logs_dir.parent == root
    assert get_settings().static_path.parent.name.startswith("mc-admin-pytest-")
    assert get_settings().database_url == f"sqlite+aiosqlite:///{root / 'runtime.sqlite3'}"
    assert get_settings().restic is None
    assert ARCHIVE_UPLOAD_TMP_DIR.parent == get_settings().static_path.parent


def test_non_docker_tests_cannot_connect_through_sdk():
    import docker

    with pytest.raises(RuntimeError, match="requires @pytest.mark.docker"):
        docker.APIClient()


def test_non_docker_tests_cannot_spawn_docker():
    with pytest.raises(RuntimeError, match="requires @pytest.mark.docker"):
        subprocess.run(["docker", "rm", "-f", "not-owned"], check=False)


def test_owned_process_gate_cannot_bypass_docker_capability_guard():
    gate = BACKEND / "app/operations/process_gate.py"
    with pytest.raises(RuntimeError, match="requires @pytest.mark.docker"):
        subprocess.run([sys.executable, str(gate), "99", "docker", "version"], check=False)


async def test_operation_runner_cannot_bypass_docker_capability_guard():
    from app.operations.processes import spawn_process

    with pytest.raises(RuntimeError, match="requires @pytest.mark.docker"):
        await spawn_process("docker", "version")


@pytest.mark.parametrize("kind", ["container", "network"])
async def test_cleanup_rejects_another_owner(monkeypatch, tmp_path, kind):
    resources = OwnedDockerResources(tmp_path)
    calls = []

    async def command(*args):
        calls.append(args)
        labels = {OWNER_LABEL: "another-test"}
        return json.dumps([{"Id": "foreign-id", "Config": {"Labels": labels}, "Labels": labels}])

    monkeypatch.setattr("tests.fixtures.test_utils.exec_command", command)
    with pytest.raises(RuntimeError, match="Refusing to remove"):
        await resources.remove(kind, "reused-name")
    assert calls == [("docker", kind, "inspect", "reused-name")]


async def test_cleanup_uses_verified_ids_and_attempts_every_resource(monkeypatch, tmp_path):
    resources = OwnedDockerResources(tmp_path)
    resources.compose(resources.name("first"), 25565, 25575)
    resources.compose(resources.name("second"), 25566, 25576)
    calls = []

    async def command(*args):
        calls.append(args)
        if args[1:3] == ("network", "ls"):
            return "owned-network\n"
        if args[2] == "inspect":
            labels = {OWNER_LABEL: resources.owner}
            return json.dumps([{"Id": args[-1] + "-id", "Config": {"Labels": labels}, "Labels": labels}])
        if args[-1] == resources.containers[-1] + "-id":
            raise RuntimeError("synthetic removal failure")
        return ""

    monkeypatch.setattr("tests.fixtures.test_utils.exec_command", command)
    with pytest.raises(ExceptionGroup, match="cleanup failed"):
        await resources.cleanup()
    assert ("docker", "rm", "-f", resources.containers[0] + "-id") in calls
    assert ("docker", "network", "rm", "owned-network-id") in calls


def test_resource_names_are_unique(tmp_path):
    first, second = OwnedDockerResources(tmp_path / "first"), OwnedDockerResources(tmp_path / "second")
    assert first.name("server") != second.name("server")


def test_default_instance_tests_do_not_invoke_docker(tmp_path):
    marker = tmp_path / "docker-was-called"
    binary = tmp_path / "docker"
    binary.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n")
    binary.chmod(0o755)
    manifest = tmp_path / "collection.json"
    environment = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}")
    result = run_pytest(["tests/test_instance.py", "--collection-manifest", str(manifest)], environment=environment)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed, 1 deselected" in result.stdout
    assert not marker.exists()
    inventory = json.loads(manifest.read_text())
    assert len(inventory["selected"]) == 2
    assert len(inventory["collected"]) == 3
    assert all("with_docker" not in nodeid for nodeid in inventory["selected"])


def test_collection_audit_rejects_omissions_and_duplicates():
    expected = {"collected": [
        {"nodeid": "tests/test_a.py::test_a", "group": "root", "capabilities": []},
        {"nodeid": "tests/new/test_b.py::test_b", "group": "new", "capabilities": ["restic"]},
    ]}
    assert matrix(expected) == {"include": [
        {"test_group": "new", "capabilities": ["restic"]},
        {"test_group": "root", "capabilities": []},
    ]}
    first = {"selected": [expected["collected"][0]["nodeid"]]}
    second = {"selected": [expected["collected"][1]["nodeid"]]}
    audit(expected, [first, second])
    with pytest.raises(ValueError, match="missing="):
        audit(expected, [first])
    with pytest.raises(ValueError, match="duplicated="):
        audit(expected, [first, second, first])


@pytest.mark.parametrize("target,mutation", [
    ("tests/snapshots/test_time_restriction.py", "from app.routers import snapshots\nasync def allow():\n    pass\nsnapshots._check_backup_time_restriction = allow\n"),
    ("tests/test_audit.py", "from app.audit import OperationAuditMiddleware\nOperationAuditMiddleware._should_audit_request = lambda self, request: False\n"),
])
def test_known_wrong_behavior_fails_the_regression_suite(tmp_path, target, mutation):
    plugin = tmp_path / "deliberately_wrong.py"
    plugin.write_text("def pytest_sessionstart(session):\n" + "\n".join("    " + line for line in mutation.splitlines()) + "\n")
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(BACKEND)]))
    result = run_pytest(["-p", "deliberately_wrong", target], environment=environment)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "failed" in result.stdout
    assert "ERROR" not in result.stdout
