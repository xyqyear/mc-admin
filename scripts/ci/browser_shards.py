"""Plan and audit serial browser case shards with owned fixture costs."""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def seconds(value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("Timing costs must be finite nonnegative seconds, with positive case estimates")
    return float(value)


def inventory(document: dict[str, Any]) -> list[dict[str, Any]]:
    if type(document.get("schema_version")) is not int or document.get("schema_version") != 1 or not document.get("cases"):
        raise ValueError("Browser inventory is empty or unsupported")
    cases = document["cases"]
    ids = []
    for case in cases:
        fields = [case["project"], case["file"], *case["titles"]]
        if not all(isinstance(field, str) and field for field in fields) or len(fields) < 3:
            raise ValueError("Browser cases require project, relative file and full titles")
        if Path(case["file"]).is_absolute() or ".." in Path(case["file"]).parts:
            raise ValueError("Browser files must be relative to the frontend")
        if case["id"] != json.dumps(fields, separators=(",", ":"), ensure_ascii=False):
            raise ValueError("Browser case identity differs from its project/file/full title")
        if not isinstance(case["groups"], list) or not all(isinstance(label, str) and label for label in case["groups"]):
            raise ValueError("Browser groups require explicit nonempty names")
        ids.append(case["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Browser inventory contains duplicate identities")
    return sorted(cases, key=lambda case: case["id"])


def atomic_groups(cases: list[dict[str, Any]]) -> list[list[str]]:
    parents = {case["id"]: case["id"] for case in cases}
    labels: dict[str, str] = {}

    def owner(case_id: str) -> str:
        while parents[case_id] != case_id:
            case_id = parents[case_id]
        return case_id

    for case in cases:
        for label in case["groups"]:
            prior = labels.setdefault(label, case["id"])
            parents[owner(case["id"])] = owner(prior)
    groups: dict[str, list[str]] = {}
    for case in cases:
        groups.setdefault(owner(case["id"]), []).append(case["id"])
    return sorted(groups.values())


def plan(document: dict[str, Any], history: dict[str, Any], candidate: dict[str, Any], *, target: float = 300, maximum: int = 8) -> dict[str, Any]:
    cases = inventory(document)
    target = seconds(target, positive=True)
    if type(maximum) is not int or maximum < 1:
        raise ValueError("Browser shard limit must be positive")
    rejection = None
    try:
        if history and (type(history.get("schema_version")) is not int or history.get("schema_version") != 1 or history.get("component") != "browser" or history.get("profile") != "default" or history.get("audited") is not True):
            raise ValueError("Browser history is not an audited compatible family envelope")
        costs = history.get("costs", {})
        if history and (not isinstance(costs, dict) or type(costs.get("schema_version")) is not int or costs.get("schema_version") != 1 or not isinstance(costs.get("cases"), dict)):
            raise ValueError("Unsupported browser cost history")
        known = {key: seconds(value, positive=True) for key, value in costs.get("cases", {}).items()}
        setup = seconds(costs.get("setup_seconds", 60))
        cleanup = seconds(costs.get("cleanup_seconds", 15))
        overhead = seconds(costs.get("command_overhead_seconds", 5))
    except (ValueError, TypeError, AttributeError) as error:
        rejection = str(error)
        known, setup, cleanup, overhead = {}, 60.0, 15.0, 5.0
    estimates = {case["id"]: known.get(case["id"], 60.0) for case in cases}
    fixed = setup + cleanup + overhead
    groups = [(sum(estimates[case_id] for case_id in group), group) for group in atomic_groups(cases)]
    groups.sort(key=lambda row: (-row[0], row[1]))
    oversized = [{"cases": group, "estimated_seconds": fixed + cost, "reason": "fixture and indivisible group exceed target"} for cost, group in groups if fixed + cost > target]
    oversized_ids = {row["cases"][0] for row in oversized}
    oversized_groups = {frozenset(row["cases"]) for row in oversized}
    count = 1 if fixed >= target else min(maximum, len(groups))
    buckets: list[dict[str, Any]] = []
    for size in range(max(1, min(len(oversized), count)), count + 1):
        buckets = [{"index": index + 1, "cases": [], "estimated_seconds": fixed} for index in range(size)]
        occupied: set[int] = set()
        for cost, group in groups:
            options = [bucket for bucket in buckets if bucket["index"] not in occupied] or buckets
            bucket = min(options, key=lambda row: (row["estimated_seconds"], row["index"]))
            bucket["cases"].extend(group)
            bucket["estimated_seconds"] += cost
            if group[0] in oversized_ids:
                occupied.add(bucket["index"])
        if all(bucket["cases"] for bucket in buckets) and all(bucket["estimated_seconds"] <= target or frozenset(bucket["cases"]) in oversized_groups for bucket in buckets):
            break
    source_sha = candidate["source"]["revision"]
    if candidate["source"].get("dirty") is not False or not candidate.get("config_digest"):
        raise ValueError("Browser plan requires a clean candidate identity")
    target_met = all(bucket["estimated_seconds"] <= target for bucket in buckets)
    reasons = []
    if fixed >= target:
        reasons.append("fixed_overhead")
    elif oversized:
        reasons.append("indivisible_unit")
    if not target_met and fixed < target and len(buckets) == maximum and any(bucket["estimated_seconds"] > target and frozenset(bucket["cases"]) not in oversized_groups for bucket in buckets):
        reasons.append("shard_limit")
    value = {"schema_version": 1, "component": "browser", "source_sha": source_sha, "image_id": candidate["config_digest"],
             "history_sha256": digest(history), "history_source": history.get("source") if rejection is None else None,
             "history_rejection": rejection, "inventory_sha256": digest(cases),
             "target_seconds": target, "max_shards": maximum, "setup_seconds": setup, "cleanup_seconds": cleanup,
             "command_overhead_seconds": overhead, "inventory": cases, "estimates": estimates, "oversized": oversized,
             "shards": buckets, "target_met": target_met, "unmet_reasons": reasons}
    value["plan_sha256"] = digest(value)
    return value


def validate_plan(value: dict[str, Any], document: dict[str, Any]) -> list[dict[str, Any]]:
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1 or value.get("component") != "browser" or value.get("plan_sha256") != digest({key: row for key, row in value.items() if key != "plan_sha256"}):
        raise ValueError("Browser plan identity is invalid")
    cases = inventory(document)
    if value["inventory_sha256"] != digest(cases) or value["inventory"] != cases:
        raise ValueError("Browser plan differs from the current inventory")
    expected = [case["id"] for case in cases]
    shards = value["shards"]
    if type(value.get("max_shards")) is not int or value["max_shards"] < 1 or len(shards) > value["max_shards"] or any(type(shard["index"]) is not int for shard in shards):
        raise ValueError("Browser shard limits and indices require positive integers")
    assigned = [case_id for shard in shards for case_id in shard["cases"]]
    if not shards or [shard["index"] for shard in shards] != list(range(1, len(shards) + 1)) or any(not shard["cases"] for shard in shards) or Counter(assigned) != Counter(expected):
        raise ValueError("Browser assignments must cover the complete inventory exactly once")
    owners = {case_id: shard["index"] for shard in shards for case_id in shard["cases"]}
    if any(len({owners[case_id] for case_id in group}) != 1 for group in atomic_groups(cases)):
        raise ValueError("Browser plan splits an indivisible fixture group")
    return cases


def select(value: dict[str, Any], index: int, directory: Path) -> None:
    cases = validate_plan(value, {"schema_version": 1, "cases": value["inventory"]})
    shard = next((row for row in value["shards"] if row["index"] == index), None)
    if shard is None:
        raise ValueError("Unknown browser shard")
    selected = set(shard["cases"])
    entries = [" › ".join([f"[{case['project']}]", case["file"], *case["titles"]]) for case in cases if case["id"] in selected]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "test-list.txt").write_text("\n".join(entries) + "\n")
    (directory / "environment.txt").write_text(f"BROWSER_PLAN_SHA256={value['plan_sha256']}\nBROWSER_HISTORY_SHA256={value['history_sha256']}\nBROWSER_SOURCE_SHA={value['source_sha']}\nBROWSER_SHARD={index}\n")


def audit(value: dict[str, Any], document: dict[str, Any], directories: list[Path], candidate: dict[str, Any]) -> dict[str, Any]:
    validate_plan(value, document)
    if value["source_sha"] != candidate["source"]["revision"] or value["image_id"] != candidate["config_digest"] or candidate["source"].get("dirty") is not False:
        raise ValueError("Browser audit candidate differs from the immutable plan")
    seen: set[int] = set()
    measured: dict[str, float] = {}
    setup, cleanup, overhead = [], [], []
    run_ids: set[str] = set()
    for directory in directories:
        report = json.loads((directory / "shard-report.json").read_text())
        index = report["shard"]
        shard = next((row for row in value["shards"] if row["index"] == index), None)
        if type(report.get("schema_version")) is not int or report.get("schema_version") != 1 or type(index) is not int or shard is None or index in seen or report.get("status") != "passed":
            raise ValueError("Browser shard is missing, duplicated or unsuccessful")
        seen.add(index)
        if any(report.get(key) != value[key] for key in ("plan_sha256", "history_sha256", "source_sha")) or Counter(report["selected"]) != Counter(shard["cases"]):
            raise ValueError("Browser shard selection or execution identity differs from its plan")
        results = report["results"]
        if Counter(row["id"] for row in results) != Counter(shard["cases"]):
            raise ValueError("Browser shard omitted, duplicated or added a case")
        for row in results:
            if row["status"] != "passed" or type(row["retry"]) is not int or row["retry"] != 0 or row["id"] in measured:
                raise ValueError("Browser history requires every case to pass exactly once without retries")
            measured[row["id"]] = max(seconds(row["seconds"]), 0.001)
        fixture = json.loads((directory / "fixture-result.json").read_text())
        manifest = json.loads((directory / "manifest.json").read_text())
        evidence = json.loads((directory / "candidate-evidence.json").read_text())
        if fixture.get("success") is not True or fixture.get("recipe") != "world" or fixture.get("image_id") != value["image_id"]:
            raise ValueError("Browser fixture failed or used another world/candidate")
        if not fixture.get("run_id") or fixture["run_id"] in run_ids or fixture["run_id"] != manifest.get("run_id") or evidence.get("run_id") != fixture["run_id"]:
            raise ValueError("Browser shards must use distinct owned run identities")
        run_ids.add(fixture["run_id"])
        if manifest.get("image") != value["image_id"] or not manifest.get("environments") or any(row.get("cleaned") is not True for row in manifest["environments"]):
            raise ValueError("Browser owned cleanup is incomplete")
        if evidence.get("source") != candidate["source"] or evidence.get("config_digest") != value["image_id"] or evidence.get("oci_manifest_digest") != candidate["oci_manifest_digest"] or evidence.get("report_sha256") != hashlib.sha256((directory / "fixture-result.json").read_bytes()).hexdigest() or evidence.get("owned_cleanup_complete") is not True or evidence.get("kind") != "browser":
            raise ValueError("Browser candidate evidence is inconsistent")
        phases = fixture["timings"]
        setup.append(seconds(phases["setup_seconds"]))
        cleanup.append(seconds(phases["cleanup_seconds"]))
        command = seconds(phases["command_seconds"])
        command_cases = sum(measured[row["id"]] for row in results)
        if command + 0.1 < command_cases:
            raise ValueError("Serial case timings exceed the owned command envelope")
        overhead.append(max(0, command - command_cases))
    if seen != {row["index"] for row in value["shards"]}:
        raise ValueError("Browser audit is missing planned shards")
    return {"schema_version": 1, "cases": measured, "setup_seconds": mean(setup), "cleanup_seconds": mean(cleanup), "command_overhead_seconds": mean(overhead)}


def write(filename: Path, value: Any) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "select", "audit"))
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--shard", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=float, default=300)
    parser.add_argument("--max-shards", type=int, default=8)
    parser.add_argument("reports", nargs="*", type=Path)
    args = parser.parse_args()
    if args.action == "plan":
        if args.inventory is None or args.candidate is None or args.history is None:
            parser.error("plan requires inventory, history and candidate")
        value = plan(json.loads(args.inventory.read_text()), json.loads(args.history.read_text()), json.loads(args.candidate.read_text()), target=args.target, maximum=args.max_shards)
        write(args.output, value)
        print(json.dumps({"include": [{"shard": row["index"]} for row in value["shards"]]}))
    else:
        if args.plan is None:
            parser.error("select and audit require a plan")
        value = json.loads(args.plan.read_text())
        if args.action == "select":
            if args.shard is None:
                parser.error("select requires a shard")
            select(value, args.shard, args.output)
        else:
            if args.inventory is None or args.candidate is None:
                parser.error("audit requires the current inventory and candidate")
            costs = audit(value, json.loads(args.inventory.read_text()), args.reports, json.loads(args.candidate.read_text()))
            write(args.output / "costs.json", costs)
            write(args.output / "browser-audit.json", {"schema_version": 1, "audited": True, "source_sha": value["source_sha"], "plan_sha256": value["plan_sha256"], "cases": len(costs["cases"]), "shards": len(value["shards"]), "target_met": value["target_met"], "unmet_reasons": value["unmet_reasons"], "oversized": value["oversized"]})


if __name__ == "__main__":
    main()
