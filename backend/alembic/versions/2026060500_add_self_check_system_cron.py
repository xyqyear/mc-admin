"""add self-check history and system cron flag

Revision ID: 2026060500
Revises: 2026052400
Create Date: 2026-06-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2026060500"
down_revision: Union[str, Sequence[str], None] = "2026052400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cronjob",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "self_check_run",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("check_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_json", sa.TEXT(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_self_check_run_finished_at"),
        "self_check_run",
        ["finished_at"],
        unique=False,
    )
    op.create_index(
        "idx_self_check_run_scope_finished_id",
        "self_check_run",
        ["scope", "finished_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_self_check_run_scope_check_finished_id",
        "self_check_run",
        ["scope", "check_id", "finished_at", "id"],
        unique=False,
    )
    op.create_table(
        "self_check_finding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("check_id", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("server_id", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.TEXT(), nullable=False),
        sa.Column("evidence_json", sa.TEXT(), nullable=False),
        sa.Column("remediation_json", sa.TEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_self_check_finding_run",
        "self_check_finding",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("self_check_finding")
    op.drop_table("self_check_run")
    op.drop_column("cronjob", "is_system")
