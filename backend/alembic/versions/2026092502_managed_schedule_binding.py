"""Bind managed restart plans only when retained evidence identifies an incarnation.

Revision ID: 2026092502
Revises: 2026092501
"""

import json
import logging
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "2026092502"
down_revision: str | Sequence[str] | None = "2026092501"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _time(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def binding_report(connection) -> list[dict]:
    jobs = list(connection.execute(sa.text(
        "SELECT cronjob_id,name,params_json,created_at,updated_at FROM cronjob "
        "WHERE identifier='restart_server' AND substr(name,1,8)='restart-'"
    )).mappings())
    servers = list(connection.execute(sa.text(
        "SELECT id,server_id,status,created_at,updated_at FROM server"
    )).mappings())
    report = []
    for job in jobs:
        name_server = job["name"][len("restart-"):]
        generation = None
        issue = None
        try:
            params = json.loads(job["params_json"])
        except (ValueError, TypeError):
            params = None
        if not isinstance(params, dict) or not isinstance(params.get("server_id"), str):
            issue = "invalid_params"
        elif params["server_id"] != name_server:
            issue = "name_params_mismatch"
        else:
            histories = [server for server in servers if server["server_id"] == name_server]
            start, end = _time(job["created_at"]), _time(job["updated_at"])
            if not histories:
                issue = "server_missing"
            elif start is None or end is None or end < start:
                issue = "generation_uncertain"
            else:
                covering, overlapping = [], []
                for server in histories:
                    created = _time(server["created_at"])
                    removed = _time(server["updated_at"]) if server["status"] == "REMOVED" else None
                    if created is None or server["status"] not in ("ACTIVE", "REMOVED") or (
                        server["status"] == "REMOVED" and (removed is None or removed < created)
                    ):
                        overlapping.append(server["id"])
                        continue
                    if created <= end and (removed is None or removed >= start):
                        overlapping.append(server["id"])
                    if created <= start and (removed is None or removed >= end):
                        covering.append(server["id"])
                if len(covering) == len(overlapping) == 1:
                    generation = covering[0]
                else:
                    issue = "generation_uncertain"
        report.append({"cronjob_id": job["cronjob_id"], "server_id": name_server,
                       "generation": generation, "issue": issue})
    generations = Counter(item["generation"] for item in report if item["generation"] is not None)
    for item in report:
        if item["generation"] is not None and generations[item["generation"]] > 1:
            item["generation"] = None
            item["issue"] = "duplicate_candidates"
    return report


def upgrade() -> None:
    connection = op.get_bind()
    report = binding_report(connection)
    if connection.dialect.name == "sqlite":
        # SQLite legacy transaction mode defers BEGIN until DML, leaving batch DDL outside rollback.
        connection.execute(sa.text("UPDATE cronjob SET id=id WHERE 0"))
    with op.batch_alter_table("cronjob") as batch:
        batch.add_column(sa.Column("managed_server_generation", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("managed_purpose", sa.String(40), nullable=True))
        batch.add_column(sa.Column("managed_binding_issue", sa.String(80), nullable=True))
        batch.create_check_constraint(
            "ck_cronjob_managed_binding",
            "(managed_purpose IS NULL AND managed_server_generation IS NULL AND managed_binding_issue IS NULL) OR "
            "(managed_purpose IS NOT NULL AND ((managed_server_generation IS NOT NULL AND managed_binding_issue IS NULL) OR "
            "(managed_server_generation IS NULL AND managed_binding_issue IS NOT NULL)))",
        )
    for item in report:
        connection.execute(sa.text(
            "UPDATE cronjob SET managed_server_generation=:generation, "
            "managed_purpose='restart', managed_binding_issue=:issue WHERE cronjob_id=:cronjob_id"
        ), item)
        if item["issue"]:
            logging.getLogger("alembic.runtime.migration").warning(
                "Managed schedule binding unresolved: cronjob_id=%s reason=%s; retained without reassignment",
                item["cronjob_id"], item["issue"],
            )
    op.create_index("uq_cronjob_managed_binding", "cronjob",
                    ["managed_server_generation", "managed_purpose"], unique=True)


def downgrade() -> None:
    connection = op.get_bind()
    bound = connection.execute(sa.text(
        "SELECT cronjob_id FROM cronjob WHERE managed_purpose IS NOT NULL LIMIT 1"
    )).first()
    if bound is not None:
        raise RuntimeError("仍有受管计划绑定或历史归属报告，不能删除身份保护；请保留当前数据库并使用兼容版本")
    if connection.dialect.name == "sqlite":
        connection.execute(sa.text("UPDATE cronjob SET id=id WHERE 0"))
    op.drop_index("uq_cronjob_managed_binding", table_name="cronjob")
    with op.batch_alter_table("cronjob") as batch:
        batch.drop_constraint("ck_cronjob_managed_binding", type_="check")
        batch.drop_column("managed_binding_issue")
        batch.drop_column("managed_purpose")
        batch.drop_column("managed_server_generation")
