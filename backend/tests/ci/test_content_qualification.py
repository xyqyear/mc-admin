import copy
import importlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
candidate = importlib.import_module("scripts.release.candidate")
content = importlib.import_module("scripts.release.content")
metadata = importlib.import_module("scripts.release.metadata")
reuse = importlib.import_module("scripts.release.reuse")


def commit(root):
    content.git(root, "add", "--all")
    content.git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "test: record fixture")
    return content.git(root, "rev-parse", "HEAD").decode().strip()


def notes(version="1.0.0"):
    return json.dumps([{"version": version, "date": "2026-10-31", "title": "版本说明", "description": "内容"}]).encode()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    content.git(root, "init", "-q")
    for path, value in {content.RELEASE_PATH: notes(), "app.py": b"original implementation", "README.md": b"documentation",
                        "tests/fixture.md": b"business fixture", ".github/workflows/docker-image.yml": b"verification policy"}.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value)
    commit(root)
    return root


def image(directory, source):
    directory.mkdir(exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        metadata.add(archive, "app/code.py", b"tested application bytes")
        metadata.add(archive, metadata.IMAGE_PATH, notes())
    payload = buffer.getvalue()
    config = metadata.encoded({"architecture": "amd64", "os": "linux", "rootfs": {"type": "layers", "diff_ids": [candidate.digest(payload)]},
                               "config": {"Cmd": ["run-original"], "Env": ["ORIGINAL=yes"]}})
    manifest = metadata.encoded({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                 "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": candidate.digest(config), "size": len(config)},
                                 "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar", "digest": candidate.digest(payload), "size": len(payload)}]})
    index = metadata.encoded({"schemaVersion": 2, "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": candidate.digest(manifest), "size": len(manifest)}]})
    with tarfile.open(directory / "application.oci.tar", "w") as archive:
        metadata.add(archive, "oci-layout", b'{"imageLayoutVersion":"1.0.0"}')
        metadata.add(archive, "index.json", index)
        for value in (payload, config, manifest):
            metadata.add(archive, "blobs/sha256/" + candidate.digest(value)[7:], value)
    (directory / "mc-admin-e2e").write_bytes(b"tested runner")
    return candidate.capture(directory, source)


def environment(monkeypatch, root, run="100"):
    for key, value in {"GITHUB_SHA": content.git(root, "rev-parse", "HEAD").decode().strip(), "GITHUB_REPOSITORY": "owner/repo",
                       "GITHUB_RUN_ID": run, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/feature"}.items():
        monkeypatch.setenv(key, value)


def results(mode):
    required = candidate.REQUIRED_GATES if mode == "full" else {"metadata"} if mode == "metadata" else set()
    return {name: {"result": "success" if name == "resolve" or name in required else "skipped"}
            for name in {"resolve", "metadata", *candidate.REQUIRED_GATES}}


def qualified(root, directory, monkeypatch):
    environment(monkeypatch, root)
    plan = reuse.resolve(root, directory, force_full=True)
    image(directory, plan["source"])
    return reuse.finalize(root, directory, plan, results("full"), "candidate-100")


class History:
    def __init__(self, receipt, directory, *, missing=False, trusted=True):
        self.receipt, self.directory, self.missing, self.trusted = receipt, directory, missing, trusted

    def artifacts(self, name, run_id=None):
        if run_id:
            return [] if self.missing else [{"id": 2}]
        source = self.receipt["producer"]
        return [{"id": 1, "workflow_run": {"id": int(source["run_id"]), "head_sha": source["sha"], "repository_id": 1, "head_repository_id": 1}}]

    def trusted_run(self, source):
        return self.trusted

    def download(self, artifact, directory, names):
        directory.mkdir(parents=True, exist_ok=True)
        if artifact["id"] == 1:
            reuse.write(directory / "qualification.json", self.receipt)
        else:
            for name in names:
                shutil.copyfile(self.directory / name, directory / name)


def test_docs_and_commit_identity_do_not_change_content_but_release_data_does(repository):
    original = content.identity(repository)
    (repository / "README.md").write_text("new explanation")
    commit(repository)
    assert content.identity(repository) == original
    (repository / content.RELEASE_PATH).write_bytes(notes("1.0.1"))
    commit(repository)
    changed = content.identity(repository)
    assert changed["verification"] == original["verification"]
    assert changed["release"] != original["release"]


@pytest.mark.parametrize("path", ["app.py", "tests/fixture.md", "new-file", "Dockerfile", "backend/uv.lock", ".github/workflows/docker-image.yml", "scripts/release/content.py"])
def test_all_effective_and_unknown_inputs_invalidate_qualification(repository, path):
    original = content.identity(repository)
    destination = repository / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("changed input")
    commit(repository)
    assert content.identity(repository)["verification"] != original["verification"]


def test_path_mode_and_deletion_invalidate_identity(repository):
    original = content.identity(repository)
    content.git(repository, "update-index", "--chmod=+x", "app.py")
    content.git(repository, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "test: executable")
    assert content.identity(repository) != original
    original = content.identity(repository)
    (repository / "app.py").rename(repository / "renamed.py")
    commit(repository)
    assert content.identity(repository) != original
    original = content.identity(repository)
    (repository / "renamed.py").unlink()
    commit(repository)
    assert content.identity(repository) != original


def test_data_derivation_preserves_code_layers_and_runtime_config(tmp_path):
    directory = tmp_path / "candidate"
    image(directory, {"revision": "a" * 40, "dirty": False, "fingerprint": "sha256:" + "b" * 64})
    source = directory / "application.oci.tar"
    derived = tmp_path / "derived.tar"
    metadata.derive(source, derived, notes("1.0.1"))
    with tarfile.open(source) as before, tarfile.open(derived) as after:
        _, base_manifest, base_config = metadata.documents(before)
        _, manifest, config = metadata.documents(after)
        assert manifest["layers"][:-1] == base_manifest["layers"]
        assert config["config"] == base_config["config"]
        for descriptor in base_manifest["layers"]:
            name = "blobs/sha256/" + descriptor["digest"][7:]
            assert metadata.read(before, name) == metadata.read(after, name)
        with tarfile.open(fileobj=io.BytesIO(metadata.read(after, "blobs/sha256/" + manifest["layers"][-1]["digest"][7:]))) as added:
            assert added.getnames() == [metadata.IMAGE_PATH]
            assert metadata.read(added, metadata.IMAGE_PATH) == notes("1.0.1")
    with pytest.raises(ValueError):
        metadata.verify_derivation(source, derived, notes("1.0.2"))
    with pytest.raises(ValueError):
        metadata.verify_derivation(derived, source, notes("1.0.1"))


def test_full_then_metadata_then_docs_keep_original_age_and_smoke(repository, tmp_path, monkeypatch):
    base = tmp_path / "base"
    original = qualified(repository, base, monkeypatch)
    (repository / content.RELEASE_PATH).write_bytes(notes("1.0.1"))
    commit(repository)
    environment(monkeypatch, repository, "101")
    derived = tmp_path / "derived"
    plan = reuse.resolve(repository, derived, client=History(original, base))
    assert plan["mode"] == "metadata"
    item = candidate.verify(derived)
    smoke = {key: item[key] for key in ("source", "config_digest", "oci_manifest_digest")}
    smoke.update(kind="browser", owned_cleanup_complete=True)
    with pytest.raises(ValueError, match="smoke"):
        reuse.finalize(repository, derived, plan, results("metadata"), "candidate-101")
    updated = reuse.finalize(repository, derived, plan, results("metadata"), "candidate-101", smoke)
    assert updated["original"] == original["original"]
    (repository / "README.md").write_text("documentation only")
    commit(repository)
    environment(monkeypatch, repository, "102")
    copied = tmp_path / "copied"
    plan = reuse.resolve(repository, copied, client=History(updated, derived))
    assert plan["mode"] == "reuse"
    final = reuse.finalize(repository, copied, plan, results("reuse"), "candidate-102")
    assert final["original"] == original["original"]
    assert final["data_evidence"] == updated["data_evidence"]
    assert final["candidate"]["oci_manifest_digest"] == updated["candidate"]["oci_manifest_digest"]
    assert final["candidate"]["source"]["revision"] != updated["candidate"]["source"]["revision"]
    reuse.validate_receipt(final, repository)
    del final["data_evidence"]
    with pytest.raises(ValueError, match="smoke"):
        reuse.validate_receipt(final, repository)


@pytest.mark.parametrize("failure", ["missing", "untrusted", "expired", "force"])
def test_unavailable_evidence_falls_back_to_full(repository, tmp_path, monkeypatch, failure):
    base = tmp_path / "base"
    value = qualified(repository, base, monkeypatch)
    environment(monkeypatch, repository, "101")
    if failure == "expired":
        value["original"]["verified_at"] = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    plan = reuse.resolve(repository, tmp_path / "restored", force_full=failure == "force",
                         client=History(value, base, missing=failure == "missing", trusted=failure != "untrusted"))
    assert plan["mode"] == "full"


@pytest.mark.parametrize("gate", sorted(candidate.REQUIRED_GATES))
@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped"])
def test_failed_complete_gates_cannot_issue_receipt(repository, tmp_path, monkeypatch, gate, outcome):
    environment(monkeypatch, repository)
    directory = tmp_path / "candidate"
    plan = reuse.resolve(repository, directory, force_full=True)
    image(directory, plan["source"])
    needs = results("full")
    needs[gate]["result"] = outcome
    with pytest.raises(ValueError, match="finish"):
        reuse.finalize(repository, directory, plan, needs, "candidate-100")


def test_corrupt_candidate_or_incomplete_receipt_fails_closed(repository, tmp_path, monkeypatch):
    base = tmp_path / "base"
    value = qualified(repository, base, monkeypatch)
    environment(monkeypatch, repository, "101")
    bad = copy.deepcopy(value)
    del bad["original"]["gates"]["browser"]
    with pytest.raises(ValueError):
        reuse.resolve(repository, tmp_path / "first", client=History(bad, base))
    (base / "mc-admin-e2e").write_text("unverified runner")
    with pytest.raises(ValueError, match="executable"):
        reuse.resolve(repository, tmp_path / "second", client=History(value, base))


def test_trust_checks_require_same_repository_workflow_source_attempt_and_success(monkeypatch):
    client = reuse.GitHub("owner/repo")
    source = {"repository": "owner/repo", "run_id": "1", "attempt": "1", "sha": "a" * 40}
    run = {"path": reuse.WORKFLOW, "event": "workflow_dispatch", "conclusion": "success", "status": "completed",
           "head_sha": source["sha"], "run_attempt": 1, "repository": {"id": 1}, "head_repository": {"id": 1}}
    monkeypatch.setattr(client, "api", lambda _: run)
    assert client.trusted_run(source)
    for key, value in [("event", "pull_request"), ("path", ".github/workflows/other.yml"), ("conclusion", "failure"),
                       ("status", "in_progress"), ("head_sha", "b" * 40), ("run_attempt", 2), ("head_repository", {"id": 2})]:
        changed = {**run, key: value}
        monkeypatch.setattr(client, "api", lambda _, changed=changed: changed)
        assert not client.trusted_run(source)


def test_unified_workflow_routes_keep_full_audits_and_final_metadata_smoke():
    workflow = yaml.safe_load((ROOT / ".github/workflows/qualification.yml").read_text())
    jobs = workflow["jobs"]
    assert set(jobs["qualification"]["needs"]) == {"resolve", "metadata", *candidate.REQUIRED_GATES}
    for name in candidate.REQUIRED_GATES:
        assert "mode == 'full'" in jobs[name]["if"]
    assert jobs["api"]["with"]["qualification"] is True
    assert jobs["metadata"]["uses"].endswith("/release-metadata.yml")
    for name in ("static-checks", "backend-tests", "e2e-tests"):
        events = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())
        events = events.get("on", events.get(True))
        assert "push" not in events and "pull_request" not in events
    root = yaml.safe_load((ROOT / ".github/workflows/docker-image.yml").read_text())
    assert root["jobs"]["qualification"]["concurrency"]["queue"] == "max"
    assert "verification" in root["jobs"]["qualification"]["concurrency"]["group"]


@pytest.mark.parametrize("data", [b"[]", notes("01.0.0"), json.dumps([json.loads(notes())[0]] * 2).encode()])
def test_invalid_release_data_cannot_derive_an_image(data):
    with pytest.raises(ValueError):
        metadata.layer(data)


def test_tag_must_match_displayed_version():
    assert content.release_data(notes("1.0.0-rc.1"), "v1.0.0-rc.1") == "1.0.0-rc.1"
    with pytest.raises(ValueError, match="displayed"):
        content.release_data(notes(), "v1.0.1")


@pytest.mark.parametrize("fault", [None, "checksum", "extra-file", "traversal"])
def test_artifact_transport_verifies_bytes_and_exact_members(tmp_path, monkeypatch, fault):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("qualification.json", b'{"evidence":"original bytes"}')
        if fault in {"extra-file", "traversal"}:
            archive.writestr("../escape" if fault == "traversal" else "unexpected", b"rejected")
    payload = buffer.getvalue()

    def download(command, *, stdout, **kwargs):
        stdout.write(payload)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(reuse.subprocess, "run", download)
    artifact = {"id": 1, "digest": candidate.digest(payload if fault != "checksum" else b"other archive")}
    destination = tmp_path / "download"
    if fault is None:
        reuse.GitHub("owner/repo").download(artifact, destination, {"qualification.json"})
        assert (destination / "qualification.json").read_bytes() == b'{"evidence":"original bytes"}'
    else:
        with pytest.raises(ValueError):
            reuse.GitHub("owner/repo").download(artifact, destination, {"qualification.json"})
        assert not list(destination.iterdir())
        assert not (tmp_path / "escape").exists()
