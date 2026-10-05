import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.collection import digest, plan


@pytest.fixture
def timing_evidence(tmp_path):
    nodeids = ["tests/example.py::test_first", "tests/example.py::test_second"]
    expected = {"collected": [{"nodeid": nodeid, "group": "root", "capabilities": []} for nodeid in nodeids],
                "selected": nodeids}
    allocation = plan(expected, {"default_seconds": 15, "files": {"tests/example.py": 50}})
    manifest = {**expected, "shard": 1, "plan_sha256": digest(allocation)}
    report = {"schema_version": 1, "manifest_sha256": digest(manifest), "completed": True,
              "exit_status": 0, "collection_errors": [], "session_seconds": 12,
              "phases": [{"nodeid": nodeid, "phase": phase, "outcome": "passed", "duration_seconds": duration}
                         for nodeid, durations in zip(nodeids, ((0.5, 1, 0.5), (2, 4, 2)), strict=True)
                         for phase, duration in zip(("setup", "call", "teardown"), durations, strict=True)]}
    paths = {name: tmp_path / f"{name}.json" for name in ("expected", "plan", "manifest", "timing")}

    def write():
        for name, value in (("expected", expected), ("plan", allocation), ("manifest", manifest), ("timing", report)):
            paths[name].write_text(json.dumps(value))

    write()
    output = tmp_path / "reports"
    command = [sys.executable, str(Path(__file__).resolve().parents[3] / "scripts/ci/backend_timing.py"),
               str(paths["timing"]), "--output", str(output), "--inventory", str(paths["expected"]),
               "--manifests", str(paths["manifest"]), "--plan", str(paths["plan"])]
    return command, output, manifest, report, write


def test_report_exports_audited_fixture_phases_and_separates_session_overhead(timing_evidence):
    command, output, _, _, _ = timing_evidence
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    weights = json.loads((output / "weights.json").read_text())
    assert weights["files"] == {"tests/example.py": 10}
    assert weights["nodes"] == {"tests/example.py::test_first": 2, "tests/example.py::test_second": 8}
    assert weights["session_overhead_seconds"] == 2
    summary = (output / "timing-summary.md").read_text()
    assert "1 shards; 300s execution target" in summary
    assert "12.000 | 10.000" in summary
    assert (output / "test-durations.csv").read_text().splitlines() == [
        "report,nodeid,setup,call,teardown,total",
        "timing,tests/example.py::test_second,2.0,4.0,2.0,8.0",
        "timing,tests/example.py::test_first,0.5,1.0,0.5,2.0",
    ]


@pytest.mark.parametrize("mutation", ["failed", "incomplete", "assignment", "plan"])
def test_report_does_not_publish_history_for_unsuccessful_or_unbound_execution(timing_evidence, mutation):
    command, output, manifest, report, write = timing_evidence
    if mutation == "failed":
        report["phases"][0]["outcome"] = "failed"
    elif mutation == "incomplete":
        report["completed"] = False
    elif mutation == "assignment":
        manifest["selected"] = manifest["selected"][:1]
    else:
        manifest["plan_sha256"] = "unrelated"
    write()
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode != 0
    assert not (output / "weights.json").exists()
    assert not output.exists()
