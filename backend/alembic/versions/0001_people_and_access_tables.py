"""people and access tables

Revision ID: 0001
Revises: 
Create Date: 2026-11-14 15:31:37.616751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_kind', sa.Text(), nullable=False),
    sa.Column('actor_id', sa.BigInteger(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('entity', sa.Text(), nullable=True),
    sa.Column('entity_id', sa.BigInteger(), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('ip', postgresql.INET(), nullable=True),
    sa.CheckConstraint("actor_kind IN ('user','api_key','cli','system')", name=op.f('ck_audit_log_actor_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_at'), 'audit_log', ['at'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('api_keys',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('prefix', sa.Text(), nullable=False),
    sa.Column('key_hash', sa.Text(), nullable=False),
    sa.Column('scopes', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_api_keys_created_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_keys')),
    sa.UniqueConstraint('key_hash', name=op.f('uq_api_keys_key_hash'))
    )
    op.create_table('governance',
    sa.Column('id', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
    sa.Column('super_admin_user_id', sa.BigInteger(), nullable=True),
    sa.Column('super_admin_state', sa.Text(), server_default=sa.text("'none'"), nullable=False),
    sa.Column('reassign_scope', sa.Text(), server_default=sa.text("'anyone'"), nullable=False),
    sa.Column('updated_by', sa.BigInteger(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(super_admin_state = 'none') = (super_admin_user_id IS NULL)", name=op.f('ck_governance_state_matches_user')),
    sa.CheckConstraint("reassign_scope = 'anyone' OR super_admin_state = 'active'", name=op.f('ck_governance_scope_needs_admin')),
    sa.CheckConstraint("reassign_scope IN ('anyone','own_only')", name=op.f('ck_governance_scope')),
    sa.CheckConstraint("super_admin_state IN ('none','active','dormant')", name=op.f('ck_governance_state')),
    sa.CheckConstraint('id = 1', name=op.f('ck_governance_single_row')),
    sa.ForeignKeyConstraint(['super_admin_user_id'], ['users.id'], name=op.f('fk_governance_super_admin_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_governance_updated_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_governance'))
    )
    op.create_table('invites',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_invites_created_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invites')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_invites_token_hash'))
    )
    op.create_table('sessions',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('csrf_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip', postgresql.INET(), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash'))
    )
    # Flat by default (GOV-1): the one governance row exists from the start.
    op.execute("INSERT INTO governance (id) VALUES (1)")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('sessions')
    op.drop_table('invites')
    op.drop_table('governance')
    op.drop_table('api_keys')
    op.drop_table('users')
    op.drop_index(op.f('ix_audit_log_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_table('audit_log')
