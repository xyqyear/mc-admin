import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from tests.support.collection import (
    audit,
    digest,
    inventory_digest,
    matrix,
    measured_weights,
    plan,
    plan_matrix,
    validate_plan,
)


def fixture():
    cases = [
        {"nodeid": "tests/test_a.py::test_a", "group": "root", "capabilities": []},
        {"nodeid": "tests/docker/test_b.py::test_b", "group": "docker", "capabilities": ["docker"]},
        {"nodeid": "tests/cloud/test_c.py::test_c", "group": "cloud", "capabilities": ["external"]},
    ]
    return {"collected": cases, "selected": [case["nodeid"] for case in cases[:2]],
            "policy": {"docker": True, "external": False, "group": None, "expression": ""}}


def shards(expected):
    result = []
    for item in matrix(expected)["include"]:
        shard = deepcopy(expected)
        shard["policy"]["group"] = item["test_group"]
        shard["selected"] = [case["nodeid"] for case in expected["collected"] if case["group"] == item["test_group"]]
        result.append(shard)
    return result


def test_discovery_preserves_explicit_external_exclusion_and_exact_capabilities():
    expected = fixture()
    assert matrix(expected) == {"include": [
        {"test_group": "docker", "capabilities": ["docker"]},
        {"test_group": "root", "capabilities": []},
    ]}
    audit(expected, shards(expected))
    default = deepcopy(expected)
    default["selected"] = [expected["selected"][0]]
    default["policy"]["docker"] = False
    assert matrix(default) == {"include": [{"test_group": "root", "capabilities": []}]}
    audit(default, shards(default))


@pytest.mark.parametrize("mutation", ["capability", "policy", "group", "selected", "duplicate_inventory"])
def test_shard_audit_rejects_changed_capability_metadata_or_selection(mutation):
    expected = fixture()
    actual = shards(expected)
    if mutation == "capability":
        actual[0]["collected"][1]["capabilities"] = []
    elif mutation == "policy":
        actual[0]["policy"]["docker"] = False
    elif mutation == "group":
        actual[0]["policy"]["group"] = "root"
    elif mutation == "selected":
        actual[0]["selected"].append("tests/cloud/test_c.py::test_c")
    else:
        actual[0]["collected"].append(actual[0]["collected"][0])
    with pytest.raises(ValueError):
        audit(expected, actual)


def planned_fixture():
    expected = fixture()
    for name, capabilities in (("slow", ["restic"]), ("new", []), ("shared", ["fd"])):
        item = {"nodeid": f"tests/{name}/test_cases.py::test_case", "group": name, "capabilities": capabilities}
        expected["collected"].append(item)
        expected["selected"].append(item["nodeid"])
    weights = {"source": {"measurement": "contract fixture"}, "default_seconds": 5, "session_overhead_seconds": 0,
               "files": {"tests/slow/test_cases.py": 30, "tests/removed/test_old.py": 99}}
    return expected, weights


def planned_results(expected, value):
    manifests, reports = [], []
    for shard in value["shards"]:
        manifest = deepcopy(expected)
        manifest.update({"selected": shard["nodeids"], "shard": shard["index"], "plan_sha256": digest(value)})
        manifests.append(manifest)
        reports.append({"schema_version": 1, "manifest_sha256": digest(manifest), "completed": True,
                        "exit_status": 0, "collection_errors": [], "session_seconds": 0, "phases": [
                            {"nodeid": nodeid, "phase": phase, "outcome": "passed", "duration_seconds": 0.01}
                            for nodeid in shard["nodeids"] for phase in ("setup", "call", "teardown")
                        ]})
    return manifests, reports


def test_balanced_plan_is_deterministic_discovers_new_files_and_keeps_capabilities():
    expected, weights = planned_fixture()
    value = plan(expected, weights, target_seconds=15)
    reordered = deepcopy(expected)
    reordered["collected"].reverse()
    reordered["selected"].reverse()
    assert plan(reordered, weights, target_seconds=15) == value
    assert value["shard_count"] == 3
    assert value["shards"][0]["files"] == ["tests/slow/test_cases.py"]
    assert value["shards"][0]["estimated_seconds"] == 30
    assert sum(shard["estimated_seconds"] for shard in value["shards"]) == 50
    assert sorted(nodeid for shard in value["shards"] for nodeid in shard["nodeids"]) == sorted(expected["selected"])
    assert plan_matrix(value)["include"][0] == {"test_shard": 1, "shard_count": 3, "capabilities": ["restic"]}
    assert all("external" not in shard["capabilities"] for shard in value["shards"])
    manifests, reports = planned_results(expected, value)
    audit(expected, manifests, test_plan=value, timings=reports)


def test_shared_fixture_labels_join_whole_files_transitively():
    expected, weights = planned_fixture()
    expected["collected"][0]["shard_groups"] = ["shared-a"]
    expected["collected"][3]["shard_groups"] = ["shared-a", "shared-b"]
    expected["collected"][4]["shard_groups"] = ["shared-b"]
    extra = {"nodeid": "tests/test_a.py::test_second", "group": "root", "capabilities": ["7z"]}
    expected["collected"].append(extra)
    expected["selected"].append(extra["nodeid"])
    value = plan(expected, weights, target_seconds=15)
    owner = next(shard for shard in value["shards"] if extra["nodeid"] in shard["nodeids"])
    assert owner["files"] == ["tests/new/test_cases.py", "tests/slow/test_cases.py", "tests/test_a.py"]
    assert owner["capabilities"] == ["7z", "restic"]
    assert value["shard_count"] == 2


def test_plan_refuses_a_shared_fixture_boundary_split_despite_complete_coverage():
    expected, weights = planned_fixture()
    value = plan(expected, weights, target_seconds=15)
    expected["collected"][0]["shard_groups"] = ["new-shared-boundary"]
    expected["collected"][3]["shard_groups"] = ["new-shared-boundary"]
    value["inventory_sha256"] = inventory_digest(expected)
    with pytest.raises(ValueError, match="shared fixture group"):
        validate_plan(expected, value)


def test_plan_refuses_file_splitting_even_when_every_node_runs_once():
    expected, weights = planned_fixture()
    extra = {"nodeid": "tests/slow/test_cases.py::test_second", "group": "slow", "capabilities": []}
    expected["collected"].append(extra)
    expected["selected"].append(extra["nodeid"])
    value = plan(expected, weights, target_seconds=15)
    first, second = value["shards"][:2]
    first["nodeids"].remove(extra["nodeid"])
    second["nodeids"].append(extra["nodeid"])
    second["files"] = sorted([*second["files"], "tests/slow/test_cases.py"])
    with pytest.raises(ValueError, match="split a test file"):
        validate_plan(expected, value)


@pytest.mark.parametrize("invalid", [0, -1, float("inf"), float("nan"), True, "2"])
def test_planning_rejects_invalid_historical_or_default_costs(invalid):
    expected, weights = planned_fixture()
    weights["default_seconds"] = invalid
    with pytest.raises(ValueError, match="finite positive"):
        plan(expected, weights, target_seconds=15)
    weights["default_seconds"] = 5
    weights["files"]["tests/slow/test_cases.py"] = invalid
    with pytest.raises(ValueError, match="finite positive"):
        plan(expected, weights, target_seconds=15)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "capability", "index", "inventory", "policy"])
def test_plan_validation_rejects_incomplete_or_changed_assignments(mutation):
    expected, weights = planned_fixture()
    value = plan(expected, weights, target_seconds=15)
    shard = value["shards"][0]
    if mutation == "missing":
        shard["nodeids"].clear()
    elif mutation == "duplicate":
        shard["nodeids"].append(shard["nodeids"][0])
    elif mutation == "extra":
        shard["nodeids"].append("tests/unknown.py::test_surprise")
    elif mutation == "capability":
        shard["capabilities"].clear()
    elif mutation == "index":
        shard["index"] = 2
    elif mutation == "inventory":
        expected["collected"][0]["capabilities"] = ["fd"]
    else:
        expected["policy"]["docker"] = False
    with pytest.raises(ValueError):
        validate_plan(expected, value)


@pytest.mark.parametrize("mutation", [
    "plan", "policy", "inventory", "shard", "assignment", "missing_report", "duplicate_report", "identity",
    "exit", "incomplete", "collection_error", "missing_phase", "duplicate_phase", "unexpected_node", "failed",
    "skipped", "xfail", "xfail_empty", "duration", "session_duration", "missing_manifest",
])
def test_execution_audit_rejects_incomplete_failed_or_unrelated_evidence(mutation):
    expected, weights = planned_fixture()
    value = plan(expected, weights, target_seconds=15)
    manifests, reports = planned_results(expected, value)
    if mutation == "plan":
        manifests[0]["plan_sha256"] = "other-plan"
    elif mutation == "policy":
        manifests[0]["policy"]["external"] = True
    elif mutation == "inventory":
        manifests[0]["collected"][0]["capabilities"] = ["fd"]
    elif mutation == "shard":
        manifests[0]["shard"] = manifests[1]["shard"]
    elif mutation == "assignment":
        manifests[0]["selected"], manifests[1]["selected"] = manifests[1]["selected"], manifests[0]["selected"]
    elif mutation == "missing_report":
        reports.pop()
    elif mutation == "duplicate_report":
        reports.append(reports[0])
    elif mutation == "identity":
        reports[0]["manifest_sha256"] = "other-manifest"
    elif mutation == "exit":
        reports[0]["exit_status"] = 1
    elif mutation == "incomplete":
        reports[0]["completed"] = False
    elif mutation == "collection_error":
        reports[0]["collection_errors"] = ["tests/test_bad.py"]
    elif mutation == "missing_phase":
        reports[0]["phases"].pop()
    elif mutation == "duplicate_phase":
        reports[0]["phases"].append(reports[0]["phases"][0])
    elif mutation == "unexpected_node":
        reports[0]["phases"][0]["nodeid"] = "tests/test_unexpected.py::test_case"
    elif mutation in {"failed", "skipped"}:
        reports[0]["phases"][0]["outcome"] = mutation
    elif mutation in {"xfail", "xfail_empty"}:
        reports[0]["phases"][0]["wasxfail"] = "expected failure" if mutation == "xfail" else ""
    elif mutation == "duration":
        reports[0]["phases"][0]["duration_seconds"] = float("nan")
    elif mutation == "session_duration":
        reports[0]["session_seconds"] = float("nan")
    else:
        manifests.pop()
    with pytest.raises(ValueError):
        audit(expected, manifests, test_plan=value, timings=reports)


def test_planned_audit_requires_execution_reports():
    expected, weights = planned_fixture()
    value = plan(expected, weights, target_seconds=15)
    manifests, _ = planned_results(expected, value)
    with pytest.raises(ValueError, match="require execution"):
        audit(expected, manifests, test_plan=value)


def automatic_fixture(costs):
    cases = [{"nodeid": f"{file}::test_case", "group": "root", "capabilities": []} for file in costs]
    return {"collected": cases, "selected": [case["nodeid"] for case in cases]}, {
        "default_seconds": 15, "session_overhead_seconds": 0, "files": costs,
    }


def history_fixture(costs):
    return {"schema_version": 1, "audited": True, "component": "backend", "profile": "default",
            "compatibility": "f" * 64,
            "source": {"run_id": "12", "attempt": "1", "sha": "1" * 40, "branch": "feature"},
            "costs": {"session_overhead_seconds": 0, **costs}}


def test_automatic_plan_uses_one_nonempty_shard_for_a_small_inventory():
    expected, weights = planned_fixture()
    value = plan(expected, weights)
    assert value["shard_count"] == 1
    assert value["shards"][0]["estimated_seconds"] == 50
    assert value["target_met"] is True
    assert value["unmet_target_reasons"] == []
    assert value["history_status"] == "missing"
    assert value["shards"][0]["nodeids"] == sorted(expected["selected"])


def test_automatic_plan_adds_shards_when_the_total_lower_bound_does_not_fit():
    expected, weights = automatic_fixture({"tests/a.py": 180, "tests/b.py": 180,
                                           "tests/c.py": 180, "tests/d.py": 60})
    value = plan(expected, weights)
    assert value["shard_count"] == 3
    assert value["target_met"] is True
    assert [shard["estimated_seconds"] for shard in value["shards"]] == [240, 180, 180]
    assert value["shards"][0]["files"] == ["tests/a.py", "tests/d.py"]
    assert value["total_estimated_seconds"] == 600
    validate_plan(expected, value)


def test_oversized_file_is_alone_without_inflating_the_other_shard_budget():
    expected, weights = automatic_fixture({"tests/long.py": 450, "tests/a.py": 150, "tests/b.py": 150})
    value = plan(expected, weights)
    assert value["shard_count"] == 2
    assert value["shards"][0]["files"] == ["tests/long.py"]
    assert value["shards"][1]["estimated_seconds"] == 300
    assert value["target_met"] is False
    assert value["unmet_target_reasons"] == ["oversized_unit"]
    assert value["oversized_units"] == [{"files": ["tests/long.py"], "estimated_seconds": 450}]


def test_shared_fixture_cost_is_the_indivisible_lower_bound():
    expected, weights = automatic_fixture({"tests/a.py": 170, "tests/b.py": 170, "tests/c.py": 20})
    for case in expected["collected"][:2]:
        case["shard_groups"] = ["shared-server"]
    value = plan(expected, weights)
    assert value["largest_atomic_seconds"] == 340
    assert value["shards"][0]["files"] == ["tests/a.py", "tests/b.py"]
    assert value["shards"][1]["files"] == ["tests/c.py"]
    assert value["unmet_target_reasons"] == ["oversized_unit"]
    validate_plan(expected, value)


@pytest.mark.parametrize("costs,reasons", [
    ({f"tests/{index}.py": 100 for index in range(7)}, ["shard_limit"]),
    ({"tests/a.py": 600, "tests/b.py": 500, "tests/c.py": 400, "tests/d.py": 20},
     ["oversized_unit", "shard_limit"]),
])
def test_shard_capacity_preserves_complete_atoms_when_the_target_is_unreachable(costs, reasons):
    expected, weights = automatic_fixture(costs)
    value = plan(expected, weights, max_shards=2)
    assert value["shard_count"] == 2
    assert value["target_met"] is False
    assert value["unmet_target_reasons"] == reasons
    assert sorted(nodeid for shard in value["shards"] for nodeid in shard["nodeids"]) == sorted(expected["selected"])
    assert sum(shard["estimated_seconds"] for shard in value["shards"]) == sum(costs.values())
    validate_plan(expected, value)


@pytest.mark.parametrize("target,limit", [(0, 32), (float("inf"), 32), (True, 32), (300, 0), (300, True), (300, 1.5)])
def test_automatic_plan_rejects_invalid_execution_budgets(target, limit):
    expected, weights = planned_fixture()
    with pytest.raises(ValueError):
        plan(expected, weights, target_seconds=target, max_shards=limit)


def test_restored_node_costs_charge_a_positive_fallback_for_new_cases_in_an_existing_file():
    expected, fallback = automatic_fixture({"tests/a.py": 600})
    expected["collected"].append({"nodeid": "tests/a.py::test_new", "group": "root", "capabilities": ["fd"]})
    expected["selected"].append("tests/a.py::test_new")
    history = history_fixture({"default_seconds": 15, "files": {"tests/a.py": 100},
                               "nodes": {"tests/a.py::test_case": 100, "tests/removed.py::test_case": 800}})
    value = plan(expected, fallback, history=history)
    assert value["history_status"] == "restored"
    assert value["history_sha256"] == digest(history)
    assert value["weights_source"] == history["source"]
    assert value["shards"][0]["estimated_seconds"] == 115
    assert value["shards"][0]["capabilities"] == ["fd"]
    assert value["shards"][0]["nodeids"] == sorted(expected["selected"])
    assert fallback["files"]["tests/a.py"] == 600


def test_removing_the_node_charged_with_shared_fixture_setup_keeps_the_file_cost_floor():
    expected, fallback = automatic_fixture({"tests/a.py": 600})
    history = history_fixture({"default_seconds": 15, "files": {"tests/a.py": 105},
                               "nodes": {"tests/a.py::test_case": 5, "tests/a.py::test_removed": 100}})
    value = plan(expected, fallback, history=history)
    assert value["shards"][0]["estimated_seconds"] == 105
    assert value["shards"][0]["nodeids"] == expected["selected"]


def test_fixed_session_cost_repeats_per_shard_and_changes_the_count():
    expected, weights = automatic_fixture({"tests/a.py": 145, "tests/b.py": 145})
    weights["session_overhead_seconds"] = 20
    value = plan(expected, weights)
    assert value["shard_count"] == 2
    assert [shard["estimated_seconds"] for shard in value["shards"]] == [165, 165]
    assert value["total_estimated_seconds"] == 330
    assert value["target_met"] is True


@pytest.mark.parametrize("overhead", [300, 350])
def test_fixed_overhead_above_the_target_uses_a_finite_best_effort_plan(overhead):
    expected, weights = automatic_fixture({"tests/a.py": 100, "tests/b.py": 100, "tests/c.py": 100})
    weights["session_overhead_seconds"] = overhead
    value = plan(expected, weights)
    assert value["shard_count"] == 1
    assert value["shards"][0]["estimated_seconds"] == 300 + overhead
    assert value["unmet_target_reasons"] == ["fixed_overhead"]
    assert value["target_met"] is False
    validate_plan(expected, value)


def test_cold_start_has_positive_session_overhead_without_charging_ci_preparation():
    expected, weights = automatic_fixture({"tests/a.py": 100})
    del weights["session_overhead_seconds"]
    value = plan(expected, weights)
    assert value["session_overhead_seconds"] == 10
    assert value["shards"][0]["estimated_seconds"] == 110


@pytest.mark.parametrize("mutation", ["schema", "unaudited", "component", "profile", "cost", "node", "shape"])
def test_malformed_history_uses_the_entire_cold_start_snapshot(mutation):
    expected, fallback = automatic_fixture({"tests/a.py": 600})
    history = history_fixture({"default_seconds": 15, "files": {"tests/a.py": 1},
                               "nodes": {"tests/a.py::test_case": 1}})
    if mutation == "schema":
        history["schema_version"] = True
    elif mutation == "unaudited":
        history["audited"] = False
    elif mutation in {"component", "profile"}:
        history[mutation] = "other"
    elif mutation == "cost":
        history["costs"]["files"]["tests/a.py"] = -1
    elif mutation == "node":
        history["costs"]["nodes"]["tests/a.py::test_case"] = float("nan")
    else:
        history["costs"] = []
    value = plan(expected, fallback, history=history)
    assert value["history_status"] == "invalid"
    assert value["history_sha256"] is None
    assert value["shards"][0]["estimated_seconds"] == 600
    assert fallback["files"]["tests/a.py"] == 600


def test_successful_history_sums_setup_call_and_teardown_within_the_current_file():
    expected, weights = automatic_fixture({"tests/a.py": 200})
    expected["collected"].append({"nodeid": "tests/a.py::test_second", "group": "root", "capabilities": []})
    expected["selected"].append("tests/a.py::test_second")
    value = plan(expected, weights)
    manifests, reports = planned_results(expected, value)
    reports[0]["phases"][0]["duration_seconds"] = 2
    reports[0]["phases"][1]["duration_seconds"] = 3
    reports[0]["phases"][2]["duration_seconds"] = 5
    costs = measured_weights(expected, manifests, value, reports)
    assert costs["nodes"]["tests/a.py::test_case"] == 10
    assert costs["nodes"]["tests/a.py::test_second"] == pytest.approx(0.03)
    assert costs["files"] == {"tests/a.py": pytest.approx(10.03)}
    assert costs["default_seconds"] > 0


def test_history_uses_the_largest_successful_session_residual_as_fixed_overhead():
    expected, weights = automatic_fixture({"tests/a.py": 200, "tests/b.py": 200})
    value = plan(expected, weights)
    manifests, reports = planned_results(expected, value)
    reports[0]["session_seconds"] = 8.03
    reports[1]["session_seconds"] = 20.03
    costs = measured_weights(expected, manifests, value, reports)
    assert costs["session_overhead_seconds"] == pytest.approx(20)
    assert costs["files"] == {"tests/a.py": pytest.approx(0.03), "tests/b.py": pytest.approx(0.03)}


def test_failed_execution_cannot_export_fast_historical_costs():
    expected, weights = planned_fixture()
    value = plan(expected, weights)
    manifests, reports = planned_results(expected, value)
    reports[0]["phases"][0]["outcome"] = "failed"
    with pytest.raises(ValueError, match="failed, skipped or xfailed"):
        measured_weights(expected, manifests, value, reports)


def test_timing_plugin_records_failed_setup_call_teardown_and_skipped_cases(tmp_path):
    (tmp_path / "conftest.py").write_text(
        "import time\n"
        "from pathlib import Path\n"
        "from tests.support.timing import TimingRecorder\n"
        "fixture_started = time.perf_counter() - 60\n"
        "def pytest_configure(config):\n"
        "    config.pluginmanager.register(TimingRecorder(Path('timing.json'), lambda session: "
        "{'selected': [item.nodeid for item in session.items]}, started=fixture_started), 'timing-contract')\n"
    )
    (tmp_path / "test_outcomes.py").write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def setup_error():\n"
        "    raise RuntimeError('setup failure')\n"
        "@pytest.fixture\n"
        "def teardown_error():\n"
        "    yield\n"
        "    raise RuntimeError('teardown failure')\n"
        "def test_pass(): pass\n"
        "def test_call_error(): assert False\n"
        "def test_setup_error(setup_error): pass\n"
        "def test_teardown_error(teardown_error): pass\n"
        "@pytest.mark.skip(reason='intentional reporting fixture')\n"
        "def test_skip(): pass\n"
    )
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "test_outcomes.py"],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads((tmp_path / "timing.json").read_text())
    assert report["completed"] is True
    assert report["exit_status"] == 1
    assert report["collection_errors"] == []
    assert report["session_seconds"] >= 60
    failed = {(event["nodeid"].split("::")[-1], event["phase"]) for event in report["phases"] if event["outcome"] == "failed"}
    assert failed == {("test_call_error", "call"), ("test_setup_error", "setup"), ("test_teardown_error", "teardown")}
    assert any(event["outcome"] == "skipped" for event in report["phases"])
    assert all(event["duration_seconds"] >= 0 for event in report["phases"])
