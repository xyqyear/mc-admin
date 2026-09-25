"""Offline, explicitly reviewed repair of duplicate open player sessions."""

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

POLICY = "earliest-open-session-v1"


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def preview(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT session_id, player_db_id, server_db_id, joined_at, left_at, "
        "duration_seconds FROM player_session WHERE left_at IS NULL "
        "ORDER BY player_db_id, server_db_id, session_id"
    )
    columns = [column[0] for column in rows.description]
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for values in rows:
        row = dict(zip(columns, values))
        grouped.setdefault((row["player_db_id"], row["server_db_id"]), []).append(row)

    groups = []
    for (player_id, server_id), sessions in grouped.items():
        if len(sessions) < 2:
            continue
        ordered = sorted(sessions, key=lambda row: (_timestamp(row["joined_at"]), row["session_id"]))
        changes = [
            {
                "before": row,
                "after": {**row, "left_at": row["joined_at"], "duration_seconds": 0},
            }
            for row in ordered[1:]
        ]
        groups.append(
            {
                "player_db_id": player_id,
                "server_db_id": server_id,
                "canonical": ordered[0],
                "changes": changes,
            }
        )
    report: dict[str, Any] = {"policy": POLICY, "groups": groups}
    report["fingerprint"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return report


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(evidence, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def apply_reviewed_report(
    connection: sqlite3.Connection,
    report: dict[str, Any],
    evidence_path: Path,
) -> dict[str, Any]:
    final_path = evidence_path.with_name(evidence_path.name + ".committed")
    if final_path.exists():
        raise FileExistsError(f"修复完成证据已存在，不能覆盖: {final_path}")
    connection.execute("BEGIN IMMEDIATE")
    try:
        if preview(connection) != report:
            raise ValueError("未结束会话已变化或修复报告无效，请重新生成并审核预检报告")
        evidence = {
            "status": "prepared",
            "prepared_at": datetime.now(UTC).isoformat(),
            "report": report,
        }
        _write_evidence(evidence_path, evidence)
        for group in report["groups"]:
            for change in group["changes"]:
                row = change["after"]
                connection.execute(
                    "UPDATE player_session SET left_at = ?, duration_seconds = 0 "
                    "WHERE session_id = ?",
                    (row["left_at"], row["session_id"]),
                )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise

    evidence["status"] = "committed"
    evidence["committed_at"] = datetime.now(UTC).isoformat()
    # The prepared report remains complete if final evidence publication fails.
    _write_evidence(final_path, evidence)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="离线预检或按已审核报告修复重复未结束会话")
    parser.add_argument("action", choices=("preview", "apply"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    mode = "ro" if args.action == "preview" else "rw"
    database_uri = args.database.resolve().as_uri() + f"?mode={mode}"
    with closing(sqlite3.connect(database_uri, uri=True)) as connection, connection:
        if args.action == "preview":
            _write_evidence(args.report, preview(connection))
        else:
            if args.evidence is None:
                parser.error("apply 必须提供 --evidence，且应用必须已停止")
            report = json.loads(args.report.read_text(encoding="utf-8"))
            apply_reviewed_report(connection, report, args.evidence)


if __name__ == "__main__":
    main()
