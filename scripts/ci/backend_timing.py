"""Render audited pytest phase reports as a CSV and a job summary."""

import argparse
import csv
import json
from pathlib import Path


def render(reports: list[Path], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, str | float]] = []
    lines = ["## Backend test timings", "", "Durations include fixture setup and teardown.", "",
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.reports, args.output)


if __name__ == "__main__":
    main()
