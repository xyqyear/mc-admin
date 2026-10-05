"""Render audited pytest phase reports as a CSV and a job summary."""

import argparse
import csv
import json
import sys
from pathlib import Path


def render(reports: list[Path], output: Path, *, inventory: Path, manifests: list[Path], plan: Path) -> None:
    from tests.support.collection import measured_weights

    document = json.loads(plan.read_text())
    weights = measured_weights(json.loads(inventory.read_text()), [json.loads(path.read_text()) for path in manifests],
                               document, [json.loads(path.read_text()) for path in reports])
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, str | float]] = []
    lines = ["## Backend test timings", "", "Durations include fixture setup and teardown.", "",
             (f"Plan: {document['shard_count']} shards; {document['target_seconds']:g}s execution target; "
              f"history {document['history_status']}."),
             (f"Estimated largest atomic unit: {document['largest_atomic_seconds']:.3f}s; "
              f"unmet target reasons: {', '.join(document['unmet_target_reasons']) or 'none'}."), "",
             (f"Fixed session estimate per shard: {document['session_overhead_seconds']:.3f}s. "
              f"Measured maximum session residual: {weights['session_overhead_seconds']:.3f}s."), "",
             "| Report | Tests | Session seconds | Phase seconds |", "| --- | ---: | ---: | ---: |"]
    for path in sorted(reports):
        report = json.loads(path.read_text())
        totals: dict[str, dict[str, float]] = {}
        for event in report["phases"]:
            phases = totals.setdefault(event["nodeid"], {"setup": 0.0, "call": 0.0, "teardown": 0.0})
            phases[event["phase"]] += event["duration_seconds"]
        elapsed = sum(sum(phases.values()) for phases in totals.values())
        lines.append(f"| {path.stem} | {len(totals)} | {report['session_seconds']:.3f} | {elapsed:.3f} |")
        cases.extend({"report": path.stem, "nodeid": nodeid, **phases, "total": sum(phases.values())}
                     for nodeid, phases in totals.items())
    cases.sort(key=lambda case: (-float(case["total"]), str(case["nodeid"])))
    with (output / "test-durations.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["report", "nodeid", "setup", "call", "teardown", "total"])
        writer.writeheader()
        writer.writerows(cases)
    lines.extend(["", "### Longest tests", "", "| Test | Setup s | Call s | Teardown s | Total s |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    for case in cases[:20]:
        label = str(case["nodeid"]).replace("|", "\\|")
        values = " | ".join(f"{float(case[phase]):.3f}" for phase in ("setup", "call", "teardown", "total"))
        lines.append(f"| {label} | {values} |")
    lines.extend(["", "Full per-test data: `backend-test-reports/test-durations.csv`."])
    (output / "timing-summary.md").write_text("\n".join(lines) + "\n")
    (output / "weights.json").write_text(json.dumps(weights, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--manifests", type=Path, nargs="+", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    render(args.reports, args.output, inventory=args.inventory, manifests=args.manifests, plan=args.plan)


if __name__ == "__main__":
    main()
