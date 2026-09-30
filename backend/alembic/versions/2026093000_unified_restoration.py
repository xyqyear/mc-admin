"""Unify file and world restoration evidence.

Revision ID: 2026093000
Revises: 2026092503
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "2026093000"
down_revision = "2026092503"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.execute(sa.text("UPDATE restoration SET id=id WHERE 0"))
    with op.batch_alter_table("restoration") as batch:
        batch.alter_column("server_id", existing_type=sa.String(100), nullable=True)
        for name in ("scope_json", "targets_json", "protection_json"):
            batch.add_column(sa.Column(name, sa.Text(), nullable=True))
        batch.add_column(sa.Column("operation_id", sa.String(32), nullable=True))
        batch.add_column(sa.Column("rollback_of_id", sa.String(32), nullable=True))
        batch.add_column(sa.Column("entry_point", sa.String(20), nullable=True))
        batch.create_index("ix_restoration_operation_id", ["operation_id"], unique=True)
        batch.create_index("ix_restoration_rollback_of_id", ["rollback_of_id"])
    rows = list(
        connection.execute(
            sa.text(
                "SELECT id,server_id,server_generation,selection_json FROM restoration"
            )
        ).mappings()
    )
    for row in rows:
        scope = None
        try:
            selection = json.loads(row["selection_json"])
            if isinstance(selection, dict) and selection.get("type") in {
                "world",
                "dimension",
                "regions",
                "chunks",
            }:
                scope = json.dumps(
                    {
                        "version": 1,
                        "scope": {
                            "kind": "world",
                            "server_id": row["server_id"],
                            "selection": {
                                key: value
                                for key, value in selection.items()
                                if key
                                in {"type", "region_dir_relpath", "regions", "chunks"}
                            },
                        },
                    }
                )
        except (ValueError, TypeError):
            pass
        connection.execute(
            sa.text(
                "UPDATE restoration SET scope_json=:scope,targets_json=:targets,entry_point='world' WHERE id=:id"
            ),
            {
                "id": row["id"],
                "scope": scope,
                "targets": json.dumps(
                    [
                        {
                            "server_id": row["server_id"],
                            "generation": row["server_generation"],
                        },
                    ]
                ),
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    if (
        connection.execute(sa.text("SELECT id FROM restoration LIMIT 1")).first()
        is not None
    ):
        raise RuntimeError(
            "仍有恢复历史，不能删除统一恢复证据；请保留数据库并使用兼容版本"
        )
    if connection.dialect.name == "sqlite":
        connection.execute(sa.text("UPDATE restoration SET id=id WHERE 0"))
    with op.batch_alter_table("restoration") as batch:
        batch.drop_index("ix_restoration_operation_id")
        batch.drop_index("ix_restoration_rollback_of_id")
        for name in (
            "scope_json",
            "targets_json",
            "protection_json",
            "operation_id",
            "rollback_of_id",
            "entry_point",
        ):
            batch.drop_column(name)
        batch.alter_column("server_id", existing_type=sa.String(100), nullable=False)
