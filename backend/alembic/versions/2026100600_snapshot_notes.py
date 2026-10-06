"""Store notes independently of Restic snapshot identity."""

import sqlalchemy as sa

from alembic import op

revision = "2026100600"
down_revision = "2026100100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "snapshot_notes",
        sa.Column("repository_id", sa.String(64), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.CheckConstraint("length(note) <= 500", name="snapshot_note_length"),
        sa.PrimaryKeyConstraint("repository_id", "snapshot_id"),
    )


def downgrade() -> None:
    op.drop_table("snapshot_notes")
