import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("browser_shards", Path(__file__).resolve().parents[3] / "scripts/ci/browser_shards.py")
assert spec is not None and spec.loader is not None
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


def case(title, groups=()):
    fields = ["chromium", "journeys.spec.ts", "administration", title]
    return {"id": json.dumps(fields, separators=(",", ":")), "project": fields[0], "file": fields[1], "titles": fields[2:], "groups": list(groups)}


def inventory(*cases):
    return {"schema_version": 1, "cases": list(cases)}


def candidate():
    return {"source": {"revision": "a" * 40, "dirty": False, "fingerprint": "source"}, "config_digest": "sha256:image", "oci_manifest_digest": "sha256:oci"}


def history(cases, setup=10, cleanup=10):
    return {"schema_version": 1, "component": "browser", "profile": "default", "audited": True, "source": {"run_id": "previous"}, "costs": {"schema_version": 1, "cases": cases, "setup_seconds": setup, "cleanup_seconds": cleanup, "command_overhead_seconds": 0}}


def test_browser_plan_uses_history_and_repeats_world_cost_per_shard():
    cases = [case(str(index)) for index in range(4)]
    value = browser.plan(inventory(*cases), history({row["id"]: 180 for row in cases}, 60, 30), candidate())
    assert len(value["shards"]) == 4
    assert {row["estimated_seconds"] for row in value["shards"]} == {270}
    assert value["target_met"] is True
    assert sorted(case_id for shard in value["shards"] for case_id in shard["cases"]) == sorted(row["id"] for row in cases)


def test_browser_plan_keeps_shared_groups_and_dedicates_oversized_work():
    first, second, independent = case("first", ["serial"]), case("second", ["serial"]), case("independent")
    value = browser.plan(inventory(first, second, independent), history({first["id"]: 170, second["id"]: 170, independent["id"]: 20}), candidate())
    assert len(value["shards"]) == 2
    assert any(set(shard["cases"]) == {first["id"], second["id"]} for shard in value["shards"])
    assert value["oversized"][0]["estimated_seconds"] == 360
    assert value["target_met"] is False


def test_browser_plan_includes_new_cases_and_bounds_matrix():
    cases = [case(str(index)) for index in range(6)]
    value = browser.plan(inventory(*cases), {}, candidate(), maximum=2)
    assert len(value["shards"]) == 2
    assert all(value["estimates"][row["id"]] > 0 for row in cases)
    impossible = browser.plan(inventory(*cases), history({row["id"]: 400 for row in cases}), candidate(), maximum=2)
    assert len(impossible["shards"]) == 2
    assert len(impossible["oversized"]) == 6
    assert impossible["target_met"] is False
    assert "shard_limit" in impossible["unmet_reasons"]


def test_browser_fixed_overhead_does_not_multiply_worlds_without_meeting_target():
    cases = [case(str(index)) for index in range(6)]
    value = browser.plan(inventory(*cases), history({row["id"]: 10 for row in cases}, 310, 10), candidate())
    assert len(value["shards"]) == 1
    assert value["unmet_reasons"] == ["fixed_overhead"]
    assert value["target_met"] is False


@pytest.mark.parametrize("key,value", [("schema_version", True), ("component", "api"), ("profile", "other"), ("audited", False)])
def test_browser_untrusted_history_envelopes_do_not_change_scheduling(key, value):
    current = case("new")
    restored = history({current["id"]: 200})
    restored[key] = value
    planned = browser.plan(inventory(current), restored, candidate())
    assert planned["history_rejection"]
    assert planned["estimates"][current["id"]] == 60


@pytest.mark.parametrize("maximum", [True, 1.5, 0])
def test_browser_shard_count_requires_a_positive_integer(maximum):
    with pytest.raises(ValueError):
        browser.plan(inventory(case("new")), {}, candidate(), maximum=maximum)


def test_browser_invalid_history_falls_back_without_losing_cases():
    current = case("new")
    value = browser.plan(inventory(current), history({current["id"]: -1}), candidate())
    assert value["history_rejection"]
    assert value["estimates"][current["id"]] == 60
    assert value["shards"][0]["cases"] == [current["id"]]


@pytest.mark.parametrize("fault", ["schema", "limit_boolean", "limit_fraction", "index_boolean", "missing_case", "split_group"])
def test_browser_audit_validates_complete_atomic_plan_before_reading_reports(fault):
    first, second = case("first", ["serial"]), case("second", ["serial"])
    document = inventory(first, second)
    value = browser.plan(document, {}, candidate())
    if fault == "schema":
        value["schema_version"] = True
    elif fault.startswith("limit"):
        value["max_shards"] = True if fault == "limit_boolean" else 1.5
    elif fault == "index_boolean":
        value["shards"][0]["index"] = True
    elif fault == "missing_case":
        value["shards"][0]["cases"].pop()
    else:
        value["shards"] = [{"index": 1, "cases": [first["id"]]}, {"index": 2, "cases": [second["id"]]}]
    value["plan_sha256"] = browser.digest({key: row for key, row in value.items() if key != "plan_sha256"})
    with pytest.raises(ValueError):
        browser.audit(value, document, [], candidate())


def test_browser_selection_uses_project_and_full_title_for_same_file(tmp_path):
    first, second = case("first"), case("second")
    value = browser.plan(inventory(first, second), history({first["id"]: 220, second["id"]: 220}), candidate())
    browser.select(value, 1, tmp_path)
    lines = (tmp_path / "test-list.txt").read_text().splitlines()
    assert lines == ["[chromium] › journeys.spec.ts › administration › first"]
    assert ":391" not in lines[0]


def reports(tmp_path, value):
    directories = []
    for shard in value["shards"]:
        directory = tmp_path / str(shard["index"])
        directory.mkdir()
        report = {"schema_version": 1, "shard": shard["index"], "plan_sha256": value["plan_sha256"], "history_sha256": value["history_sha256"], "source_sha": value["source_sha"], "status": "passed", "selected": shard["cases"], "results": [{"id": case_id, "status": "passed", "retry": 0, "seconds": 11} for case_id in shard["cases"]]}
        fixture = {"success": True, "recipe": "world", "image_id": value["image_id"], "run_id": f"run-{shard['index']}", "timings": {"setup_seconds": 12, "command_seconds": len(shard["cases"]) * 11 + 2, "cleanup_seconds": 3}}
        manifest = {"image": value["image_id"], "run_id": fixture["run_id"], "environments": [{"id": "owned", "cleaned": True}]}
        evidence = {"source": candidate()["source"], "config_digest": value["image_id"], "oci_manifest_digest": candidate()["oci_manifest_digest"], "run_id": fixture["run_id"], "owned_cleanup_complete": True, "kind": "browser"}
        for name, payload in (("shard-report.json", report), ("fixture-result.json", fixture), ("manifest.json", manifest)):
            (directory / name).write_text(json.dumps(payload))
        evidence["report_sha256"] = hashlib.sha256((directory / "fixture-result.json").read_bytes()).hexdigest()
        (directory / "candidate-evidence.json").write_text(json.dumps(evidence))
        directories.append(directory)
    return directories


def test_browser_audit_extracts_only_complete_successful_case_and_fixture_costs(tmp_path):
    first, second = case("first"), case("second")
    document = inventory(first, second)
    value = browser.plan(document, {}, candidate())
    directories = reports(tmp_path, value)
    costs = browser.audit(value, document, directories, candidate())
    assert costs == {"schema_version": 1, "cases": {first["id"]: 11, second["id"]: 11}, "setup_seconds": 12, "cleanup_seconds": 3, "command_overhead_seconds": 2}


@pytest.mark.parametrize("fault", ["missing_case", "duplicate_case", "unexpected_case", "failed", "skipped", "retry", "history", "plan", "candidate", "cleanup", "missing_shard"])
def test_browser_audit_rejects_partial_or_inconsistent_success(tmp_path, fault):
    first, second = case("first"), case("second")
    document = inventory(first, second)
    value = browser.plan(document, {}, candidate())
    directories = reports(tmp_path, value)
    directory = directories[0]
    report = json.loads((directory / "shard-report.json").read_text())
    if fault == "missing_case":
        report["results"].pop()
    elif fault == "duplicate_case":
        report["results"].append(report["results"][0])
    elif fault == "unexpected_case":
        report["results"][0]["id"] = case("unexpected")["id"]
    elif fault in ("failed", "skipped"):
        report["results"][0]["status"] = fault
    elif fault == "retry":
        report["results"][0]["retry"] = 1
    elif fault in ("history", "plan"):
        report[f"{fault}_sha256"] = "another"
    elif fault == "candidate":
        evidence = json.loads((directory / "candidate-evidence.json").read_text())
        evidence["source"]["revision"] = "b" * 40
        (directory / "candidate-evidence.json").write_text(json.dumps(evidence))
    elif fault == "cleanup":
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["environments"][0]["cleaned"] = False
        (directory / "manifest.json").write_text(json.dumps(manifest))
    else:
        directories = []
    (directory / "shard-report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        browser.audit(value, document, directories, candidate())
