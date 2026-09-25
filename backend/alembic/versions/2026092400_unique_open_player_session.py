"""Enforce one open session per player and server.

Revision ID: 2026092400
Revises: 2026090700
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2026092400"
down_revision: str | Sequence[str] | None = "2026090700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT player_db_id, server_db_id, COUNT(*) FROM player_session "
            "WHERE left_at IS NULL GROUP BY player_db_id, server_db_id "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates is not None:
        raise RuntimeError(
            "发现重复未结束玩家会话，迁移未修改数据。请停止应用、备份数据库，"
            "使用 python -m app.db.session_repair preview 生成并审核报告，"
            "再显式 apply 修复；详见 docs/database-migrations.md"
        )
    op.create_index(
        "uq_player_session_open",
        "player_session",
        ["player_db_id", "server_db_id"],
        unique=True,
        sqlite_where=sa.text("left_at IS NULL"),
        postgresql_where=sa.text("left_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_player_session_open", table_name="player_session")
