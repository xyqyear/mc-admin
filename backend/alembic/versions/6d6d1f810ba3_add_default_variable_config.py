"""add_default_variable_config

Revision ID: 6d6d1f810ba3
Revises: f2ee81a56fee
Create Date: 2026-02-01 23:29:44.316444

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d6d1f810ba3"
down_revision: Union[str, Sequence[str], None] = "f2ee81a56fee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Table creation is handled by SQLAlchemy's Base.metadata.create_all() at app startup.
    Default data insertion is handled by the backend when no record exists.
    """
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("default_variable_config")
