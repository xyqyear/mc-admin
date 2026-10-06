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


def envelope(branch="feature", run="42", component="backend", profile="default"):
    return history["publish"](component, profile, CONTEXT, {"default_seconds": 15, "files": {"tests/a.py": 12}}, {
        "GITHUB_RUN_ID": run, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40, "GITHUB_REF_NAME": branch,
    })


def artifact(identity, branch="feature", run=42, component="backend", **changes):
    return {"id": identity, "name": f"timing-history-{component}", "expired": False, "created_at": f"2026-10-05T12:00:{identity:02d}Z",
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


@pytest.mark.parametrize("component", ["backend", "api", "browser"])
def test_restore_uses_latest_repository_sample_and_freezes_identity(component):
    client = SavedHistory(
        [artifact(5, component=component), artifact(2, "main", 21, component),
         artifact(3, "release", 33, component, created_at="2026-10-05T12:00:06Z"),
         artifact(4, "cleanup", 44, component, created_at="2026-10-05T12:00:06Z")],
        {2: envelope("main", "21", component), 3: envelope("release", "33", component),
         4: envelope("cleanup", "44", component), 5: envelope(component=component)},
    )
    value = history["restore"](client, component, "default", CONTEXT)
    assert value["source"]["branch"] == "cleanup"
    assert value["source"]["run_id"] == "44"
    assert value["artifact"] == {"id": 4, "digest": None, "repository": "owner/repo"}
    assert client.downloads == [4]


def test_restore_skips_newer_invalid_samples_for_compatible_other_branch():
    incompatible = {**envelope("feature", "43"), "compatibility": "c" * 64}
    failed = {**envelope("release", "44"), "audited": False}
    source_mismatch = {**envelope("hotfix", "45"), "source": {**envelope("hotfix", "45")["source"], "sha": "d" * 40}}
    client = SavedHistory(
        [artifact(1, "main", 21), artifact(2, "cleanup"), artifact(3, "feature", 43),
         artifact(4, "release", 44), artifact(5, "hotfix", 45)],
        {1: envelope("main", "21"), 2: envelope("cleanup"), 3: incompatible, 4: failed, 5: source_mismatch},
    )
    value = history["restore"](client, "backend", "default", CONTEXT)
    assert value["source"]["run_id"] == "42"
    assert value["source"]["branch"] == "cleanup"
    assert value["artifact"] == {"id": 2, "digest": None, "repository": "owner/repo"}
    assert client.downloads == [5, 4, 3, 2]


def test_restore_excludes_expired_fork_current_run_and_other_component():
    fork = artifact(3)
    fork["workflow_run"]["head_repository_id"] = 2
    client = SavedHistory(
        [artifact(1, "trusted-other", 21), artifact(2, expired=True), fork, artifact(4, run=99),
         artifact(5, component="api")],
        {1: envelope("trusted-other", "21")},
    )
    value = history["restore"](client, "backend", "default", CONTEXT, current_run="99")
    assert value["source"]["branch"] == "trusted-other"
    assert client.downloads == [1]
    assert history["restore"](SavedHistory([], {}), "backend", "default", CONTEXT) == {}


@pytest.mark.parametrize("change", [{"run_id": "43"}, {"sha": "d" * 40}, {"branch": "forged"}])
def test_restore_rejects_history_source_mismatch(change):
    forged = envelope()
    forged["source"].update(change)
    client = SavedHistory(
        [artifact(1, "trusted-other", 21), artifact(2)],
        {1: envelope("trusted-other", "21"), 2: forged},
    )
    value = history["restore"](client, "backend", "default", CONTEXT)
    assert value["source"]["branch"] == "trusted-other"
    assert client.downloads == [2, 1]


@pytest.mark.parametrize("component,profile,other_profile", [
    ("backend", "default", "no-reuse"), ("api", "qualification", "regression"),
    ("api", "qualification", "qualification-no-reuse"), ("browser", "default", "other"),
])
def test_restore_keeps_execution_profiles_isolated(component, profile, other_profile):
    client = SavedHistory(
        [artifact(1, "trusted-other", 21, component), artifact(2, component=component)],
        {1: envelope("trusted-other", "21", component, profile),
         2: envelope(component=component, profile=other_profile)},
    )
    value = history["restore"](client, component, profile, CONTEXT)
    assert value["source"]["branch"] == "trusted-other"
    assert value["profile"] == profile
    assert client.downloads == [2, 1]


def test_restore_searches_past_ten_incompatible_samples_across_branches():
    client = SavedHistory(
        [artifact(1, "main", 21), artifact(2, "other-feature", 22),
         *[artifact(identity, "recent-feature") for identity in range(3, 13)]],
        {1: envelope("main", "21"), 2: envelope("other-feature", "22"),
         **{identity: {**envelope("recent-feature"), "compatibility": "c" * 64} for identity in range(3, 13)}},
    )
    value = history["restore"](client, "backend", "default", CONTEXT)
    assert value["source"]["branch"] == "other-feature"
    assert value["artifact"]["id"] == 2
    assert client.downloads == list(range(12, 1, -1))


def test_artifact_inventory_bounds_repository_search_to_three_pages(monkeypatch):
    client = history["GitHubHistory"]("owner/repo")
    requests = []

    def response(endpoint):
        requests.append(endpoint)
        return json.dumps({"artifacts": [{"id": identity} for identity in range(1, 101)]}).encode()

    monkeypatch.setattr(client, "api", response)
    assert len(client.artifacts("backend")) == 300
    assert requests == [
        f"repos/owner/repo/actions/artifacts?name=timing-history-backend&per_page=100&page={page}"
        for page in (1, 2, 3)
    ]


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
