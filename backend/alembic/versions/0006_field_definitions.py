"""field_definitions and custom values on donors and gifts (CUS-1, D-141, D-146)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (entity, key, label, type, choices, required, contact, show_in_list). Position = order * 10.
BUILTINS = [
    ('donor', 'first_name', 'First name', 'text', None, False, False, False),
    ('donor', 'last_name', 'Last name', 'text', None, False, False, False),
    ('donor', 'organization', 'Organization', 'text', None, False, False, True),
    ('donor', 'email', 'Email', 'text', None, False, True, False),
    ('donor', 'phone', 'Phone', 'text', None, False, True, False),
    ('donor', 'notes', 'Notes', 'long_text', None, False, False, False),
    ('donor', 'kind', 'Kind', 'choice', ['person', 'organization', 'funder'], True, False, False),
    ('gift', 'gift_date', 'Gift date', 'date', None, True, False, False),
    ('gift', 'amount', 'Amount', 'money', None, True, False, False),
    ('gift', 'program', 'Program', 'text', None, False, False, False),
    ('gift', 'campaign', 'Campaign', 'text', None, False, False, False),
    ('gift', 'payer', 'Payer', 'text', None, False, False, False),
]


def upgrade() -> None:
    """Upgrade schema."""
    table = op.create_table(
        'field_definitions',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('entity', sa.Text(), nullable=False),
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('choices', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('is_builtin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_required', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_contact', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('show_in_list', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('position', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("entity IN ('donor','gift')", name=op.f('ck_field_definitions_entity')),
        sa.CheckConstraint(
            "type IN ('text','long_text','number','money','date','bool','choice','multi_choice')",
            name=op.f('ck_field_definitions_type'),
        ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_field_definitions_created_by_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_field_definitions')),
        sa.UniqueConstraint('entity', 'key', name='uq_field_definitions_entity_key'),
    )
    order: dict[str, int] = {}
    rows = []
    for entity, key, label, ftype, choices, required, contact, listed in BUILTINS:
        order[entity] = order.get(entity, 0) + 10
        rows.append(dict(
            entity=entity, key=key, label=label, type=ftype, choices=choices, is_builtin=True,
            is_required=required, is_contact=contact, show_in_list=listed, position=order[entity],
        ))
    op.bulk_insert(table, rows)
    for name in ('donors', 'gifts'):
        op.add_column(name, sa.Column(
            'custom', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ))
        op.create_index(f'ix_{name}_custom', name, ['custom'], postgresql_using='gin')


def downgrade() -> None:
    """Downgrade schema."""
    for name in ('gifts', 'donors'):
        op.drop_index(f'ix_{name}_custom', table_name=name, postgresql_using='gin')
        op.drop_column(name, 'custom')
    op.drop_table('field_definitions')
