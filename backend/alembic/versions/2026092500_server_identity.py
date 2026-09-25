"""Retain server incarnation IDs and prevent ambiguous active names.

Revision ID: 2026092500
Revises: 2026092400
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2026092500"
down_revision: str | Sequence[str] | None = "2026092400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate = op.get_bind().execute(sa.text(
        "SELECT server_id FROM server WHERE status='ACTIVE' "
        "GROUP BY server_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate is not None:
        raise RuntimeError(
            "发现重复的活动服务器记录，迁移未修改数据。请停止应用、备份数据库，"
            "核对重复名称对应的实例及历史引用，审核后将非当前实例标记为 REMOVED；"
            "不要删除或合并历史 ID。详见 docs/database-migrations.md"
        )
    with op.batch_alter_table(
        "server", recreate="always", table_kwargs={"sqlite_autoincrement": True}
    ):
        pass
    op.create_index(
        "uq_server_active_name", "server", ["server_id"], unique=True,
        sqlite_where=sa.text("status='ACTIVE'"),
        postgresql_where=sa.text("status='ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_server_active_name", table_name="server")
    with op.batch_alter_table(
        "server", recreate="always", table_kwargs={"sqlite_autoincrement": False}
    ):
        pass
