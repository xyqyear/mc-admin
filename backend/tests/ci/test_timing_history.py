import copy
import hashlib
import io
import json
import runpy
import zipfile
from pathlib import Path

import pytest

history = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/ci/timing_history.py"))
CONTEXT = "b" * 64


def envelope(branch="feature", run="42"):
    return history["publish"]("backend", "default", CONTEXT, {"default_seconds": 15, "files": {"tests/a.py": 12}}, {
        "GITHUB_RUN_ID": run, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40, "GITHUB_REF_NAME": branch,
    })


def artifact(identity, branch="feature", run=42, **changes):
    return {"id": identity, "name": "timing-history-backend", "expired": False, "created_at": f"2026-10-05T12:00:{identity:02d}Z",
            "workflow_run": {"id": run, "head_branch": branch, "head_sha": "a" * 40, "repository_id": 1, "head_repository_id": 1},
            **changes}


class SavedHistory:
    repository = "owner/repo"

    def __init__(self, records, values):
        self.records = records
        self.values = values
        self.downloads = []

    def artifacts(self, _component):
        return self.records

    def download(self, record):
        self.downloads.append(record["id"])
        return copy.deepcopy(self.values[record["id"]])


def test_restore_prefers_latest_comparable_branch_sample_and_freezes_identity():
    incompatible = {**envelope(), "compatibility": "c" * 64}
    failed = {**envelope(), "audited": False}
    source_mismatch = {**envelope(), "source": {**envelope()["source"], "sha": "d" * 40}}
    client = SavedHistory(
        [artifact(1, "main", 21), artifact(2), artifact(3), artifact(4), artifact(5)],
        {1: envelope("main", "21"), 2: envelope(), 3: incompatible, 4: failed, 5: source_mismatch},
    )
    value = history["restore"](client, "backend", "default", CONTEXT, "feature")
    assert value["source"]["run_id"] == "42"
    assert value["artifact"] == {"id": 2, "digest": None, "repository": "owner/repo"}
    assert client.downloads == [5, 4, 3, 2]


def test_restore_falls_back_to_main_without_learning_expired_fork_or_current_run():
    fork = artifact(3)
    fork["workflow_run"]["head_repository_id"] = 2
    client = SavedHistory(
        [artifact(1, "main", 21), artifact(2, expired=True), fork, artifact(4, run=99)],
        {1: envelope("main", "21")},
    )
    value = history["restore"](client, "backend", "default", CONTEXT, "feature", current_run="99")
    assert value["source"]["branch"] == "main"
    assert client.downloads == [1]
    assert history["restore"](SavedHistory([], {}), "backend", "default", CONTEXT, "feature") == {}


@pytest.mark.parametrize("change", [
    {"audited": False}, {"costs": {}}, {"profile": "no-reuse"}, {"schema_version": 2}, {"schema_version": True},
    {"source": {"run_id": "42", "attempt": "0", "sha": "a" * 40, "branch": "feature"}},
    {"source": {"run_id": "42", "attempt": "1", "sha": "a" * 7, "branch": "feature"}},
    {"costs": {"files": {"tests/a.py": float("nan")}}},
])
def test_history_rejects_invalid_or_incomplete_samples(change):
    with pytest.raises(ValueError):
        history["validate"]({**envelope(), **change}, "backend", "default", CONTEXT)


def test_compatibility_tracks_configuration_without_binding_to_source_sha(tmp_path):
    pinned = tmp_path / "lock"
    pinned.write_text("fixed dependencies")
    fingerprint = history["fingerprint"]
    first = fingerprint([pinned], ["workers=1", "measurement=phases-v2"])
    assert first == fingerprint([pinned], ["measurement=phases-v2", "workers=1"])
    assert first != fingerprint([pinned], ["workers=2", "measurement=phases-v2"])
    pinned.write_text("new dependencies")
    assert first != fingerprint([pinned], ["workers=1", "measurement=phases-v2"])
    a = envelope()
    b = copy.deepcopy(a)
    b["source"]["sha"] = "c" * 40
    history["validate"](b, "backend", "default", a["compatibility"])


def test_download_reads_only_one_bounded_history_and_verifies_digest(monkeypatch):
    client = history["GitHubHistory"]("owner/repo")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr("reports/history.json", json.dumps(envelope()))
        zipped.writestr("../../unrelated", "never extracted")
    data = stream.getvalue()
    monkeypatch.setattr(client, "api", lambda _endpoint: data)
    record = {**artifact(1), "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
    assert client.download(record)["costs"]["files"] == {"tests/a.py": 12}
    with pytest.raises(ValueError, match="digest"):
        client.download({**record, "digest": "sha256:" + "0" * 64})
    with zipfile.ZipFile(stream, "a") as zipped:
        zipped.writestr("other/history.json", json.dumps(envelope()))
    monkeypatch.setattr(client, "api", lambda _endpoint: stream.getvalue())
    with pytest.raises(ValueError, match="one bounded"):
        client.download(artifact(1))
