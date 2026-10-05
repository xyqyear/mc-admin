import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inventory(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = manifest["collected"]
    result = {case["nodeid"]: case for case in records}
    if len(result) != len(records):
        raise ValueError("Duplicate identities in collected inventory")
    return result


def selected(manifest: dict[str, Any]) -> list[str]:
    records = inventory(manifest)
    ids = manifest.get("selected", list(records))
    if len(ids) != len(set(ids)) or set(ids) - records.keys():
        raise ValueError("Invalid selected test identities")
    return ids


def matrix(manifest: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, set[str]] = {}
    records = inventory(manifest)
    for nodeid in selected(manifest):
        case = records[nodeid]
        groups.setdefault(case["group"], set()).update(case["capabilities"])
    return {"include": [
        {"test_group": group, "capabilities": sorted(required)}
        for group, required in sorted(groups.items())
    ]}


def selection_policy(manifest: dict[str, Any]) -> dict[str, Any]:
    policy = manifest.get("policy", {})
    return {key: policy.get(key, default) for key, default in (
        ("docker", False), ("external", False), ("group", None), ("expression", ""), ("keyword", ""),
    )}


def inventory_digest(manifest: dict[str, Any]) -> str:
    return digest({"collected": inventory(manifest), "selected": sorted(selected(manifest)),
                   "policy": selection_policy(manifest)})


def atomic_files(manifest: dict[str, Any]) -> list[list[str]]:
    records = inventory(manifest)
    parents: dict[str, str] = {}
    labels: dict[str, str] = {}

    def owner(file: str) -> str:
        parents.setdefault(file, file)
        while parents[file] != file:
            file = parents[file]
        return file

    for nodeid in sorted(selected(manifest)):
        case = records[nodeid]
        file = nodeid.split("::", 1)[0]
        owner(file)
        for label in case.get("shard_groups", []):
            prior = labels.setdefault(label, file)
            parents[owner(file)] = owner(prior)
    groups: dict[str, list[str]] = {}
    for file in sorted(parents):
        groups.setdefault(owner(file), []).append(file)
    return sorted(groups.values())


def positive_cost(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("Historical and default file costs must be finite positive seconds")
    return float(value)


def nonnegative_cost(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Session overhead must be finite nonnegative seconds")
    return float(value)


def planning_weights(manifest: dict[str, Any], fallback: dict[str, Any],
                     history: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    default = positive_cost(fallback["default_seconds"])
    files = {file: positive_cost(value) for file, value in fallback["files"].items()}
    overhead = nonnegative_cost(fallback.get("session_overhead_seconds", 10))
    weights = {**fallback, "default_seconds": default, "files": files, "session_overhead_seconds": overhead}
    if not history:
        return weights, "missing"
    try:
        if (type(history["schema_version"]) is not int or history["schema_version"] != 1 or history.get("audited") is not True
                or history["component"] != "backend" or history["profile"] != "default"):
            raise ValueError("Unrelated backend history")
        costs = history["costs"]
        default = positive_cost(costs["default_seconds"])
        overhead = nonnegative_cost(costs.get("session_overhead_seconds", 10))
        measured = {file: positive_cost(value) for file, value in costs["files"].items()}
        files = {**weights["files"], **measured}
        if "nodes" in costs:
            nodes = {nodeid: positive_cost(value) for nodeid, value in costs["nodes"].items()}
            current: dict[str, list[str]] = {}
            for nodeid in selected(manifest):
                current.setdefault(nodeid.split("::", 1)[0], []).append(nodeid)
            for file, nodeids in current.items():
                retained = math.fsum(nodes[nodeid] for nodeid in nodeids if nodeid in nodes)
                added = default * sum(nodeid not in nodes for nodeid in nodeids)
                files[file] = max(measured.get(file, 0), retained) + added
        return {**costs, "default_seconds": default, "files": files,
                "session_overhead_seconds": overhead, "source": history["source"]}, "restored"
    except (KeyError, TypeError, ValueError, AttributeError):
        return weights, "invalid"


def allocate_atoms(atoms: list[tuple[float, list[str]]], count: int) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = [{"files": [], "estimated_seconds": 0.0} for _ in range(count)]
    for cost, files in atoms:
        index = min(range(count), key=lambda index: (buckets[index]["estimated_seconds"], index))
        buckets[index]["files"].extend(files)
        buckets[index]["estimated_seconds"] += cost
    return buckets


def plan(manifest: dict[str, Any], weights: dict[str, Any], *, target_seconds: float = 300,
         max_shards: int = 32, history: dict[str, Any] | None = None) -> dict[str, Any]:
    target = positive_cost(target_seconds)
    if type(max_shards) is not int or max_shards < 1:
        raise ValueError("Maximum shard count must be a positive integer")
    weights, history_status = planning_weights(manifest, weights, history)
    default = weights["default_seconds"]
    overhead = weights["session_overhead_seconds"]
    execution_budget = target - overhead
    costs = weights["files"]
    atoms = atomic_files(manifest)
    if not atoms:
        raise ValueError("Cannot plan an empty selected inventory")
    weighted = sorted([(math.fsum(costs.get(file, default) for file in files), files) for files in atoms],
                      key=lambda item: (-item[0], item[1]))
    atomic_budget = execution_budget if execution_budget > 0 else target
    oversized = [(cost, files) for cost, files in weighted if cost > atomic_budget]
    ordinary = [(cost, files) for cost, files in weighted if cost <= atomic_budget]
    limit = min(max_shards, len(atoms))
    limited = len(oversized) + bool(ordinary) > limit
    if execution_budget <= 0:
        requested = max(len(oversized) + bool(ordinary), math.ceil(math.fsum(cost for cost, _ in weighted) / target))
        limited = requested > limit
        buckets = allocate_atoms(weighted, min(requested, limit))
    elif limited:
        buckets = allocate_atoms(weighted, limit)
    else:
        buckets = [{"files": list(files), "estimated_seconds": cost} for cost, files in oversized]
        if ordinary:
            available = min(limit - len(oversized), len(ordinary))
            first = min(available, max(1, math.ceil(math.fsum(cost for cost, _ in ordinary) / execution_budget)))
            packed = allocate_atoms(ordinary, first)
            for count in range(first + 1, available + 1):
                if max(bucket["estimated_seconds"] for bucket in packed) <= execution_budget:
                    break
                packed = allocate_atoms(ordinary, count)
            limited = max(bucket["estimated_seconds"] for bucket in packed) > execution_budget
            buckets.extend(packed)
    records = inventory(manifest)
    wanted = selected(manifest)
    for index, bucket in enumerate(buckets, start=1):
        bucket["index"] = index
        bucket["files"].sort()
        bucket["nodeids"] = sorted(nodeid for nodeid in wanted if nodeid.split("::", 1)[0] in bucket["files"])
        bucket["capabilities"] = sorted({name for nodeid in bucket["nodeids"] for name in records[nodeid]["capabilities"]})
        bucket["estimated_seconds"] = round(bucket["estimated_seconds"] + overhead, 6)
    reasons = ((["fixed_overhead"] if execution_budget <= 0 else [])
               + (["oversized_unit"] if oversized else []) + (["shard_limit"] if limited else []))
    result = {"schema_version": 1, "inventory_sha256": inventory_digest(manifest),
              "weights_sha256": digest(weights), "weights_source": weights.get("source", {}),
              "history_sha256": digest(history) if history_status == "restored" else None,
              "history_status": history_status, "target_seconds": target, "max_shards": max_shards,
              "session_overhead_seconds": overhead,
              "total_estimated_seconds": round(math.fsum(cost for cost, _ in weighted) + overhead * len(buckets), 6),
              "largest_atomic_seconds": round(weighted[0][0] + overhead, 6),
              "target_met": not reasons, "unmet_target_reasons": reasons,
              "oversized_units": [{"files": files, "estimated_seconds": round(cost + overhead, 6)}
                                  for cost, files in oversized],
              "shard_count": len(buckets), "shards": buckets}
    validate_plan(manifest, result)
    return result


def plan_matrix(value: dict[str, Any]) -> dict[str, Any]:
    return {"include": [{"test_shard": shard["index"], "shard_count": value["shard_count"],
                         "capabilities": shard["capabilities"]}
                        for shard in value["shards"]]}


def exact_union(wanted: set[str], observed: list[str]) -> None:
    counts = Counter(observed)
    missing = sorted(wanted - counts.keys())
    extra = sorted(counts.keys() - wanted)
    duplicated = sorted(nodeid for nodeid, count in counts.items() if count != 1)
    if missing or extra or duplicated:
        raise ValueError(f"Collection mismatch: missing={missing}, extra={extra}, duplicated={duplicated}")


def validate_plan(expected: dict[str, Any], value: dict[str, Any]) -> None:
    if value.get("schema_version") != 1 or value.get("inventory_sha256") != inventory_digest(expected):
        raise ValueError("Plan inventory or selection policy differs from collected inventory")
    shards = value["shards"]
    count = value["shard_count"]
    if not shards or type(count) is not int or count != len(shards):
        raise ValueError("Invalid plan shard count")
    if any(type(shard["index"]) is not int for shard in shards) or [shard["index"] for shard in shards] != list(range(1, count + 1)):
        raise ValueError("Invalid or duplicate plan shard indexes")
    exact_union(set(selected(expected)), [nodeid for shard in shards for nodeid in shard["nodeids"]])
    records = inventory(expected)
    file_owners: dict[str, int] = {}
    for shard in shards:
        files = sorted({nodeid.split("::", 1)[0] for nodeid in shard["nodeids"]})
        required = sorted({name for nodeid in shard["nodeids"] for name in records[nodeid]["capabilities"]})
        if not files or files != shard["files"] or required != shard["capabilities"]:
            raise ValueError("Plan file or capability declarations do not match selected tests")
        for file in files:
            if file in file_owners:
                raise ValueError("Plan split a test file between shards")
            file_owners[file] = shard["index"]
    if any(len({file_owners[file] for file in files}) != 1 for files in atomic_files(expected)):
        raise ValueError("Plan split a shared fixture group between shards")


def audit_execution(manifests: list[dict[str, Any]], reports: list[dict[str, Any]]) -> None:
    expected = {digest(manifest): manifest for manifest in manifests}
    observed: set[str] = set()
    for report in reports:
        identity = report.get("manifest_sha256")
        if identity not in expected or identity in observed:
            raise ValueError("Missing, unexpected or duplicate execution manifest identity")
        observed.add(identity)
        if report.get("schema_version") != 1 or report.get("completed") is not True or report.get("exit_status") != 0:
            raise ValueError("Test execution did not complete successfully")
        if report.get("collection_errors"):
            raise ValueError("Test collection reported errors")
        nonnegative_cost(report.get("session_seconds"))
        phases: dict[str, list[str]] = {}
        for event in report["phases"]:
            if event["outcome"] != "passed" or "wasxfail" in event:
                raise ValueError("Test execution contains a failed, skipped or xfailed phase")
            duration = event["duration_seconds"]
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
                raise ValueError("Invalid execution phase duration")
            phases.setdefault(event["nodeid"], []).append(event["phase"])
        if set(phases) != set(expected[identity]["selected"]) or any(
            values != ["setup", "call", "teardown"] for values in phases.values()
        ):
            raise ValueError("Execution phases are missing, duplicated, reordered or unexpected")
    if observed != expected.keys():
        raise ValueError("Missing execution reports for selected shards")


def audit(expected: dict[str, Any], shards: list[dict[str, Any]], *,
          test_plan: dict[str, Any] | None = None, timings: list[dict[str, Any]] | None = None) -> None:
    wanted = set(selected(expected))
    definitions = inventory(expected)
    if test_plan is not None:
        validate_plan(expected, test_plan)
        if len(shards) != test_plan["shard_count"]:
            raise ValueError("Missing or duplicate shard manifests")
    indexes: set[int] = set()
    for shard in shards:
        if (test_plan is not None or "collected" in shard) and inventory(shard) != definitions:
            raise ValueError("Shard collected different identities or capability declarations")
        if test_plan is not None:
            index = shard.get("shard")
            if type(index) is not int or index in indexes or not 1 <= index <= test_plan["shard_count"]:
                raise ValueError("Unexpected or duplicate execution shard index")
            indexes.add(index)
            if shard.get("plan_sha256") != digest(test_plan) or selection_policy(shard) != selection_policy(expected):
                raise ValueError("Shard plan identity or selection policy differs from inventory")
            if sorted(shard["selected"]) != test_plan["shards"][index - 1]["nodeids"]:
                raise ValueError("Shard selected tests outside its planned assignment")
        elif "policy" in expected:
            policy = expected["policy"]
            actual = shard.get("policy", {})
            if any(actual.get(key) != policy[key] for key in ("docker", "external", "expression")):
                raise ValueError("Shard capability selection policy differs from inventory")
            group = actual.get("group")
            if group is None or any(definitions[nodeid]["group"] != group for nodeid in shard["selected"] if nodeid in definitions):
                raise ValueError("Shard selected tests outside its declared group")
    exact_union(wanted, [nodeid for shard in shards for nodeid in shard["selected"]])
    if test_plan is not None and timings is None:
        raise ValueError("Planned shards require execution timing reports")
    if timings is not None:
        audit_execution(shards, timings)


def measured_weights(expected: dict[str, Any], shards: list[dict[str, Any]],
                     test_plan: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    audit(expected, shards, test_plan=test_plan, timings=reports)
    phases: dict[str, list[float]] = {}
    for report in reports:
        for event in report["phases"]:
            phases.setdefault(event["nodeid"], []).append(event["duration_seconds"])
    nodes = {nodeid: max(math.fsum(values), 0.000001) for nodeid, values in sorted(phases.items())}
    files: dict[str, list[float]] = {}
    for nodeid, seconds in nodes.items():
        files.setdefault(nodeid.split("::", 1)[0], []).append(seconds)
    overhead = max(max(0, report["session_seconds"] - math.fsum(event["duration_seconds"] for event in report["phases"]))
                   for report in reports)
    return {"schema_version": 1, "source": {"measurement": "backend-phase-v2"}, "default_seconds": 15.0,
            "session_overhead_seconds": overhead,
            "files": {file: math.fsum(values) for file, values in sorted(files.items())}, "nodes": nodes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("matrix", "plan", "audit"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("shards", nargs="*", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--target-seconds", type=float, default=300)
    parser.add_argument("--max-shards", type=int, default=32)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--timings", nargs="+", type=Path)
    args = parser.parse_args()
    expected = json.loads(args.manifest.read_text())
    if args.command == "matrix":
        print(json.dumps(matrix(expected), separators=(",", ":")))
    elif args.command == "plan":
        if args.weights is None or args.output is None:
            parser.error("plan requires --weights and --output")
        history = json.loads(args.history.read_text()) if args.history else None
        value = plan(expected, json.loads(args.weights.read_text()), target_seconds=args.target_seconds,
                     max_shards=args.max_shards, history=history)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2) + "\n")
        print(json.dumps(plan_matrix(value), separators=(",", ":")))
    else:
        audit(expected, [json.loads(path.read_text()) for path in args.shards],
              test_plan=json.loads(args.plan.read_text()) if args.plan else None,
              timings=[json.loads(path.read_text()) for path in args.timings] if args.timings else None)
        print(f"Verified {len(selected(expected))} selected test identities across {len(args.shards)} shards")


if __name__ == "__main__":
    main()
