"""Retain task results with their operation history."""

import sqlalchemy as sa

from alembic import op

revision = "2026100100"
down_revision = "2026093000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operation_journal", sa.Column("task_result_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("operation_journal") as batch:
        batch.drop_column("task_result_json")
