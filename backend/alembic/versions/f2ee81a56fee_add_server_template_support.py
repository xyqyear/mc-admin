"""Base schema through server template support

Revision ID: f2ee81a56fee
Revises:
Create Date: 2026-01-31 23:58:42.860424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2ee81a56fee'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('cronjob',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cronjob_id', sa.String(length=255), nullable=False),
    sa.Column('identifier', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('cron', sa.String(length=100), nullable=False),
    sa.Column('second', sa.String(length=20), nullable=True),
    sa.Column('params_json', sa.TEXT(), nullable=False),
    sa.Column('execution_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'PAUSED', 'CANCELLED', name='cronjobstatus'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cronjob_cronjob_id'), 'cronjob', ['cronjob_id'], unique=True)
    op.create_index(op.f('ix_cronjob_identifier'), 'cronjob', ['identifier'], unique=False)
    op.create_table('cronjob_execution',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cronjob_id', sa.String(length=255), nullable=False),
    sa.Column('execution_id', sa.String(length=50), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='executionstatus'), nullable=False),
    sa.Column('messages_json', sa.TEXT(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('execution_id')
    )
    op.create_index(op.f('ix_cronjob_execution_cronjob_id'), 'cronjob_execution', ['cronjob_id'], unique=False)
    op.create_table('default_variable_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('variable_definitions_json', sa.TEXT(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('dynamic_config',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('module_name', sa.String(length=100), nullable=False),
    sa.Column('config_data', sa.JSON(), nullable=False),
    sa.Column('config_schema_version', sa.String(length=50), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dynamic_config_module_name'), 'dynamic_config', ['module_name'], unique=True)
    op.create_table('player',
    sa.Column('player_db_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('uuid', sa.String(length=32), nullable=False),
    sa.Column('current_name', sa.String(length=16), nullable=False),
    sa.Column('skin_data', sa.LargeBinary(), nullable=True),
    sa.Column('avatar_data', sa.LargeBinary(), nullable=True),
    sa.Column('last_skin_update', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('player_db_id')
    )
    op.create_index(op.f('ix_player_uuid'), 'player', ['uuid'], unique=True)
    op.create_table('player_achievement',
    sa.Column('achievement_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('player_db_id', sa.Integer(), nullable=False),
    sa.Column('server_db_id', sa.Integer(), nullable=False),
    sa.Column('achievement_name', sa.String(length=255), nullable=False),
    sa.Column('earned_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('achievement_id')
    )
    op.create_index('idx_player_achievement_player_time', 'player_achievement', ['player_db_id', 'earned_at'], unique=False)
    op.create_index('idx_player_achievement_server_time', 'player_achievement', ['server_db_id', 'earned_at'], unique=False)
    op.create_index('idx_player_achievement_time', 'player_achievement', ['earned_at'], unique=False)
    op.create_index('idx_player_achievement_unique', 'player_achievement', ['player_db_id', 'server_db_id', 'achievement_name'], unique=True)
    op.create_index(op.f('ix_player_achievement_player_db_id'), 'player_achievement', ['player_db_id'], unique=False)
    op.create_index(op.f('ix_player_achievement_server_db_id'), 'player_achievement', ['server_db_id'], unique=False)
    op.create_table('player_chat_message',
    sa.Column('message_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('player_db_id', sa.Integer(), nullable=False),
    sa.Column('server_db_id', sa.Integer(), nullable=False),
    sa.Column('message_text', sa.TEXT(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('message_id')
    )
    op.create_index('idx_player_chat_player_time', 'player_chat_message', ['player_db_id', 'sent_at'], unique=False)
    op.create_index('idx_player_chat_server_time', 'player_chat_message', ['server_db_id', 'sent_at'], unique=False)
    op.create_index(op.f('ix_player_chat_message_player_db_id'), 'player_chat_message', ['player_db_id'], unique=False)
    op.create_index(op.f('ix_player_chat_message_server_db_id'), 'player_chat_message', ['server_db_id'], unique=False)
    op.create_table('player_session',
    sa.Column('session_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('player_db_id', sa.Integer(), nullable=False),
    sa.Column('server_db_id', sa.Integer(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('session_id')
    )
    op.create_index('idx_player_session_player_left_at', 'player_session', ['player_db_id', 'left_at'], unique=False)
    op.create_index('idx_player_session_player_server_online', 'player_session', ['player_db_id', 'server_db_id', 'left_at'], unique=False)
    op.create_index('idx_player_session_player_time', 'player_session', ['player_db_id', 'joined_at'], unique=False)
    op.create_index('idx_player_session_server_online', 'player_session', ['server_db_id', 'left_at'], unique=False)
    op.create_index('idx_player_session_server_time', 'player_session', ['server_db_id', 'joined_at'], unique=False)
    op.create_index(op.f('ix_player_session_player_db_id'), 'player_session', ['player_db_id'], unique=False)
    op.create_index(op.f('ix_player_session_server_db_id'), 'player_session', ['server_db_id'], unique=False)
    op.create_table('server',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('server_id', sa.String(length=100), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'REMOVED', name='serverstatus'), nullable=False),
    sa.Column('template_id', sa.Integer(), nullable=True),
    sa.Column('template_snapshot_json', sa.TEXT(), nullable=True),
    sa.Column('variable_values_json', sa.TEXT(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_server_server_id'), 'server', ['server_id'], unique=False)
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
    op.create_table('system_heartbeat',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=True),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('ADMIN', 'OWNER', name='userrole'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_username'), table_name='user')
    op.drop_table('user')
    op.drop_table('system_heartbeat')
    op.drop_index(op.f('ix_server_template_name'), table_name='server_template')
    op.drop_table('server_template')
    op.drop_index(op.f('ix_server_server_id'), table_name='server')
    op.drop_table('server')
    op.drop_index(op.f('ix_player_session_server_db_id'), table_name='player_session')
    op.drop_index(op.f('ix_player_session_player_db_id'), table_name='player_session')
    op.drop_index('idx_player_session_server_time', table_name='player_session')
    op.drop_index('idx_player_session_server_online', table_name='player_session')
    op.drop_index('idx_player_session_player_time', table_name='player_session')
    op.drop_index('idx_player_session_player_server_online', table_name='player_session')
    op.drop_index('idx_player_session_player_left_at', table_name='player_session')
    op.drop_table('player_session')
    op.drop_index(op.f('ix_player_chat_message_server_db_id'), table_name='player_chat_message')
    op.drop_index(op.f('ix_player_chat_message_player_db_id'), table_name='player_chat_message')
    op.drop_index('idx_player_chat_server_time', table_name='player_chat_message')
    op.drop_index('idx_player_chat_player_time', table_name='player_chat_message')
    op.drop_table('player_chat_message')
    op.drop_index(op.f('ix_player_achievement_server_db_id'), table_name='player_achievement')
    op.drop_index(op.f('ix_player_achievement_player_db_id'), table_name='player_achievement')
    op.drop_index('idx_player_achievement_unique', table_name='player_achievement')
    op.drop_index('idx_player_achievement_time', table_name='player_achievement')
    op.drop_index('idx_player_achievement_server_time', table_name='player_achievement')
    op.drop_index('idx_player_achievement_player_time', table_name='player_achievement')
    op.drop_table('player_achievement')
    op.drop_index(op.f('ix_player_uuid'), table_name='player')
    op.drop_table('player')
    op.drop_index(op.f('ix_dynamic_config_module_name'), table_name='dynamic_config')
    op.drop_table('dynamic_config')
    op.drop_table('default_variable_config')
    op.drop_index(op.f('ix_cronjob_execution_cronjob_id'), table_name='cronjob_execution')
    op.drop_table('cronjob_execution')
    op.drop_index(op.f('ix_cronjob_identifier'), table_name='cronjob')
    op.drop_index(op.f('ix_cronjob_cronjob_id'), table_name='cronjob')
    op.drop_table('cronjob')
