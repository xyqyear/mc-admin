"""Retain safe authored task failures across application restarts."""

import sqlalchemy as sa

from alembic import op

revision = "2026101800"
down_revision = "2026100700"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operation_journal", sa.Column("failure_message", sa.String(4096), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("operation_journal") as batch:
        batch.drop_column("failure_message")
