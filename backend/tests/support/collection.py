import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


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


def audit(expected: dict[str, Any], shards: list[dict[str, Any]]) -> None:
    wanted = set(selected(expected))
    definitions = inventory(expected)
    for shard in shards:
        if "collected" in shard and inventory(shard) != definitions:
            raise ValueError("Shard collected different identities or capability declarations")
        if "policy" in expected:
            policy = expected["policy"]
            actual = shard.get("policy", {})
            if any(actual.get(key) != policy[key] for key in ("docker", "external", "expression")):
                raise ValueError("Shard capability selection policy differs from inventory")
            group = actual.get("group")
            if group is None or any(definitions[nodeid]["group"] != group for nodeid in shard["selected"] if nodeid in definitions):
                raise ValueError("Shard selected tests outside its declared group")
    observed = Counter(nodeid for shard in shards for nodeid in shard["selected"])
    missing = sorted(wanted - observed.keys())
    extra = sorted(observed.keys() - wanted)
    duplicated = sorted(nodeid for nodeid, count in observed.items() if count != 1)
    if missing or extra or duplicated:
        raise ValueError(f"Collection mismatch: missing={missing}, extra={extra}, duplicated={duplicated}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("matrix", "audit"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("shards", nargs="*", type=Path)
    args = parser.parse_args()
    expected = json.loads(args.manifest.read_text())
    if args.command == "matrix":
        print(json.dumps(matrix(expected), separators=(",", ":")))
    else:
        audit(expected, [json.loads(path.read_text()) for path in args.shards])
        print(f"Verified {len(expected['collected'])} test identities across {len(args.shards)} groups")


if __name__ == "__main__":
    main()
