"""Add server template support

Revision ID: f2ee81a56fee
Revises: ba4b4a1fb5a8
Create Date: 2026-01-31 23:58:42.860424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2ee81a56fee'
down_revision: Union[str, Sequence[str], None] = 'ba4b4a1fb5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create server_template table
    op.create_table('server_template',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.TEXT(), nullable=True),
    sa.Column('yaml_template', sa.TEXT(), nullable=False),
    sa.Column('variable_definitions_json', sa.TEXT(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_server_template_name'), 'server_template', ['name'], unique=True)

    # Create default_variable_config table
    op.create_table('default_variable_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('variable_definitions_json', sa.TEXT(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    # Add template-related columns to server table
    op.add_column('server', sa.Column('template_id', sa.Integer(), nullable=True))
    op.add_column('server', sa.Column('template_snapshot_json', sa.TEXT(), nullable=True))
    op.add_column('server', sa.Column('variable_values_json', sa.TEXT(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('server', 'variable_values_json')
    op.drop_column('server', 'template_snapshot_json')
    op.drop_column('server', 'template_id')
    op.drop_table('default_variable_config')
    op.drop_index(op.f('ix_server_template_name'), table_name='server_template')
    op.drop_table('server_template')
