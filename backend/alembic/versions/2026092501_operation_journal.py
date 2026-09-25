"""Retain consequential operation state and owned recovery evidence.

Revision ID: 2026092501
Revises: 2026092500
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2026092501"
down_revision: str | Sequence[str] | None = "2026092500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_journal",
        sa.Column("operation_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("legacy_id", sa.String(64), nullable=True),
        sa.Column("running_intent", sa.Boolean(), nullable=True),
        sa.Column("configuration_version", sa.String(64), nullable=True),
        sa.Column("resources_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("phase", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_changed", sa.Boolean(), nullable=False),
        sa.Column("writers_stopped", sa.Boolean(), nullable=False),
        sa.Column("ownership_known", sa.Boolean(), nullable=False),
        sa.Column("processes_json", sa.Text(), nullable=False),
        sa.Column("recovery_refs_json", sa.Text(), nullable=False),
        sa.Column("has_recovery_refs", sa.Boolean(), nullable=False),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("blocked_reason", sa.String(64), nullable=True),
        sa.Column("cache_degraded", sa.Boolean(), nullable=False),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("origin", "legacy_id", name="uq_operation_journal_legacy"),
    )
    op.create_index("ix_operation_journal_state_updated", "operation_journal", ["state", "updated_at"])
    op.create_index("ix_operation_journal_retention", "operation_journal", ["writers_stopped", "has_recovery_refs", "ended_at"])


def downgrade() -> None:
    connection = op.get_bind()
    protected = connection.execute(sa.text(
        "SELECT operation_id FROM operation_journal WHERE writers_stopped = 0 "
        "OR blocked_reason IS NOT NULL OR has_recovery_refs = 1 OR cache_degraded = 1 "
        "OR state IN ('queued','running','cancelling','finalizing') LIMIT 1"
    )).first()
    if protected is not None:
        raise RuntimeError("仍有活动操作或未解决的恢复记录，拒绝删除操作日志；请先停止应用并处理恢复事项")
    op.drop_index("ix_operation_journal_retention", table_name="operation_journal")
    op.drop_index("ix_operation_journal_state_updated", table_name="operation_journal")
    op.drop_table("operation_journal")
