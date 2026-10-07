"""Resolve restart schedules by their configured server name."""

import sqlalchemy as sa

from alembic import op

revision = "2026100700"
down_revision = "2026100600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        # SQLite legacy transaction mode leaves batch DDL outside rollback until DML starts a transaction.
        connection.execute(sa.text("UPDATE cronjob SET id=id WHERE 0"))
    op.drop_index("uq_cronjob_managed_binding", table_name="cronjob")
    with op.batch_alter_table("cronjob") as batch:
        batch.drop_constraint("ck_cronjob_managed_binding", type_="check")
        batch.drop_column("managed_server_generation")
        batch.drop_column("managed_binding_issue")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text(
        "SELECT id FROM cronjob WHERE managed_purpose IS NOT NULL LIMIT 1"
    )).first() is not None:
        raise RuntimeError("仍有按服务器名管理的重启计划，不能恢复实例绑定；请保留当前数据库并使用兼容版本")
    if connection.dialect.name == "sqlite":
        connection.execute(sa.text("UPDATE cronjob SET id=id WHERE 0"))
    with op.batch_alter_table("cronjob") as batch:
        batch.add_column(sa.Column("managed_server_generation", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("managed_binding_issue", sa.String(80), nullable=True))
        batch.create_check_constraint(
            "ck_cronjob_managed_binding",
            "(managed_purpose IS NULL AND managed_server_generation IS NULL AND managed_binding_issue IS NULL) OR "
            "(managed_purpose IS NOT NULL AND ((managed_server_generation IS NOT NULL AND managed_binding_issue IS NULL) OR "
            "(managed_server_generation IS NULL AND managed_binding_issue IS NOT NULL)))",
        )
    op.create_index("uq_cronjob_managed_binding", "cronjob",
                    ["managed_server_generation", "managed_purpose"], unique=True)
