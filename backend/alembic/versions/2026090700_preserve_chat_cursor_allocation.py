"""preserve chat cursor allocation after cleanup

Revision ID: 2026090700
Revises: 2026060500
Create Date: 2026-09-07 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "2026090700"
down_revision: str | Sequence[str] | None = "2026060500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table(
        "player_chat_message",
        recreate="always",
        table_kwargs={"sqlite_autoincrement": True},
    ):
        pass


def downgrade() -> None:
    with op.batch_alter_table(
        "player_chat_message",
        recreate="always",
        table_kwargs={"sqlite_autoincrement": False},
    ):
        pass
