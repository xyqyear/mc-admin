"""Preserve restoration ownership across server name reuse.

Revision ID: 2026092503
Revises: 2026092502
"""

import logging
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "2026092503"
down_revision = "2026092502"
branch_labels = None
depends_on = None


def _time(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def binding_report(connection) -> list[dict]:
    servers = list(connection.execute(sa.text(
        "SELECT id,server_id,status,created_at,updated_at FROM server"
    )).mappings())
    report = []
    for row in connection.execute(sa.text(
        "SELECT id,server_id,started_at,finished_at FROM restoration"
    )).mappings():
        start = _time(row["started_at"])
        end = _time(row["finished_at"]) if row["finished_at"] is not None else start
        histories = [server for server in servers if server["server_id"] == row["server_id"]]
        covering, overlapping = [], []
        if start is not None and end is not None and end >= start:
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
        generation = covering[0] if len(covering) == len(overlapping) == 1 else None
        report.append({"id": row["id"], "generation": generation,
                       "issue": None if generation is not None else (
                           "generation_uncertain" if histories else "server_missing")})
    return report


def upgrade() -> None:
    connection = op.get_bind()
    report = binding_report(connection)
    if connection.dialect.name == "sqlite":
        connection.execute(sa.text("UPDATE restoration SET id=id WHERE 0"))
    with op.batch_alter_table("restoration") as batch:
        batch.add_column(sa.Column("server_generation", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("binding_issue", sa.String(80), nullable=True))
    for item in report:
        connection.execute(sa.text(
            "UPDATE restoration SET server_generation=:generation, binding_issue=:issue WHERE id=:id"
        ), item)
        if item["issue"]:
            logging.getLogger("alembic.runtime.migration").warning(
                "Restoration binding unresolved: restoration_id=%s reason=%s; history and snapshots retained",
                item["id"], item["issue"],
            )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT id FROM restoration LIMIT 1")).first() is not None:
        raise RuntimeError("仍有恢复历史，不能删除实例归属保护；请保留当前数据库并使用兼容版本")
    if connection.dialect.name == "sqlite":
        connection.execute(sa.text("UPDATE restoration SET id=id WHERE 0"))
    with op.batch_alter_table("restoration") as batch:
        batch.drop_column("binding_issue")
        batch.drop_column("server_generation")
