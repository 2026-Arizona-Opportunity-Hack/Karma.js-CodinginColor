"""super_admin_nominations (GOV-2, D-144)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'super_admin_nominations',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('nominee_user_id', sa.BigInteger(), nullable=False),
        sa.Column('nominated_by', sa.BigInteger(), nullable=False),
        sa.Column('confirmed_by', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','confirmed','cancelled','expired')", name=op.f('ck_super_admin_nominations_status')),
        sa.ForeignKeyConstraint(['nominee_user_id'], ['users.id'], name=op.f('fk_super_admin_nominations_nominee_user_id_users')),
        sa.ForeignKeyConstraint(['nominated_by'], ['users.id'], name=op.f('fk_super_admin_nominations_nominated_by_users')),
        sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], name=op.f('fk_super_admin_nominations_confirmed_by_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_super_admin_nominations')),
    )
    op.create_index(
        'uq_super_admin_nominations_one_pending',
        'super_admin_nominations',
        ['status'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_super_admin_nominations_one_pending', table_name='super_admin_nominations')
    op.drop_table('super_admin_nominations')
