"""imports and relationship tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 16:56:12.390320

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('app_settings',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings'))
    )
    op.create_table('digest_runs',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('triggered_by', sa.BigInteger(), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('recipients', sa.Integer(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.CheckConstraint("mode IN ('dry_run','live')", name=op.f('ck_digest_runs_mode')),
    sa.ForeignKeyConstraint(['triggered_by'], ['users.id'], name=op.f('fk_digest_runs_triggered_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_digest_runs'))
    )
    op.create_table('message_templates',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('channel', sa.Text(), nullable=False),
    sa.Column('subject', sa.Text(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('updated_by', sa.BigInteger(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel IN ('email','sms')", name=op.f('ck_message_templates_channel')),
    sa.CheckConstraint("kind IN ('thank_you','quarterly_update','lapsed_nudge','event_invite')", name=op.f('ck_message_templates_kind')),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_message_templates_updated_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_message_templates')),
    sa.UniqueConstraint('kind', 'channel', name=op.f('uq_message_templates_kind'))
    )
    op.create_table('next_steps',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('donor_id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('status', sa.Text(), server_default=sa.text("'open'"), nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(status = 'done') = (done_at IS NOT NULL)", name=op.f('ck_next_steps_done_at_matches')),
    sa.CheckConstraint("status IN ('open','done','cancelled')", name=op.f('ck_next_steps_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_next_steps_created_by_users')),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], name=op.f('fk_next_steps_donor_id_donors')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_next_steps'))
    )
    op.create_index('uq_next_steps_one_open', 'next_steps', ['donor_id'], unique=True, postgresql_where=sa.text("status = 'open'"))
    op.create_table('import_rows',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('normalized', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('row_key', sa.Text(), nullable=True),
    sa.Column('gift_id', sa.BigInteger(), nullable=True),
    sa.Column('donor_id', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("status <> 'invalid' OR reason IS NOT NULL", name=op.f('ck_import_rows_invalid_has_reason')),
    sa.CheckConstraint("status IN ('new','already_imported','needs_review','invalid','donor_new','donor_matched')", name=op.f('ck_import_rows_status')),
    sa.ForeignKeyConstraint(['batch_id'], ['import_batches.id'], name=op.f('fk_import_rows_batch_id_import_batches')),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], name=op.f('fk_import_rows_donor_id_donors')),
    sa.ForeignKeyConstraint(['gift_id'], ['gifts.id'], name=op.f('fk_import_rows_gift_id_gifts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_rows'))
    )
    op.create_index('ix_import_rows_row_key', 'import_rows', ['row_key'], unique=False)
    op.create_index('uq_import_rows_batch_row', 'import_rows', ['batch_id', 'row_number'], unique=True)
    op.create_table('messages',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('donor_id', sa.BigInteger(), nullable=False),
    sa.Column('gift_id', sa.BigInteger(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('channel', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('subject', sa.Text(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('body_sha256_at_approval', sa.Text(), nullable=True),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('approved_by', sa.BigInteger(), nullable=True),
    sa.Column('sent_by', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivery_mode', sa.Text(), nullable=True),
    sa.Column('provider_ref', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.CheckConstraint("channel IN ('email','sms')", name=op.f('ck_messages_channel')),
    sa.CheckConstraint("delivery_mode IS NULL OR delivery_mode IN ('dry_run','live','manual')", name=op.f('ck_messages_delivery_mode')),
    sa.CheckConstraint("kind IN ('thank_you','quarterly_update','lapsed_nudge','event_invite')", name=op.f('ck_messages_kind')),
    sa.CheckConstraint("status <> 'approved' OR (approved_by IS NOT NULL AND body_sha256_at_approval IS NOT NULL)", name=op.f('ck_messages_approved_has_approver')),
    sa.CheckConstraint("status IN ('draft','approved','sent','sent_manually','cancelled','failed')", name=op.f('ck_messages_status')),
    sa.CheckConstraint("status NOT IN ('sent','sent_manually') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND sent_at IS NOT NULL)", name=op.f('ck_messages_sent_was_approved')),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], name=op.f('fk_messages_approved_by_users')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_messages_created_by_users')),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], name=op.f('fk_messages_donor_id_donors')),
    sa.ForeignKeyConstraint(['gift_id'], ['gifts.id'], name=op.f('fk_messages_gift_id_gifts')),
    sa.ForeignKeyConstraint(['sent_by'], ['users.id'], name=op.f('fk_messages_sent_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index('ix_messages_donor', 'messages', ['donor_id', 'created_at'], unique=False)
    op.create_index('uq_messages_open_per_donor_kind', 'messages', ['donor_id', 'kind'], unique=True, postgresql_where=sa.text("status IN ('draft','approved') AND kind <> 'thank_you'"))
    op.create_index('uq_messages_open_thank_you_per_gift', 'messages', ['gift_id'], unique=True, postgresql_where=sa.text("kind = 'thank_you' AND status IN ('draft','approved')"))
    op.create_table('interactions',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('donor_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('occurred_on', sa.Date(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('message_id', sa.BigInteger(), nullable=True),
    sa.Column('gift_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('call','text','email','meeting','note','thank_you','update','system')", name=op.f('ck_interactions_kind')),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], name=op.f('fk_interactions_donor_id_donors')),
    sa.ForeignKeyConstraint(['gift_id'], ['gifts.id'], name=op.f('fk_interactions_gift_id_gifts')),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_interactions_message_id_messages')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_interactions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interactions'))
    )
    op.create_index('ix_interactions_donor_date', 'interactions', ['donor_id', 'occurred_on'], unique=False)
    op.create_table('match_reviews',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('import_row_id', sa.BigInteger(), nullable=True),
    sa.Column('gift_id', sa.BigInteger(), nullable=True),
    sa.Column('incoming', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('candidate_donor_ids', postgresql.ARRAY(sa.BigInteger()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('status', sa.Text(), server_default=sa.text("'open'"), nullable=False),
    sa.Column('decided_by', sa.BigInteger(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(status = 'open') = (decided_at IS NULL AND decided_by IS NULL)", name=op.f('ck_match_reviews_decision_recorded')),
    sa.CheckConstraint("status IN ('open','linked','created_new','anonymous')", name=op.f('ck_match_reviews_status')),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_match_reviews_decided_by_users')),
    sa.ForeignKeyConstraint(['gift_id'], ['gifts.id'], name=op.f('fk_match_reviews_gift_id_gifts')),
    sa.ForeignKeyConstraint(['import_row_id'], ['import_rows.id'], name=op.f('fk_match_reviews_import_row_id_import_rows')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_match_reviews'))
    )
    op.create_index('ix_match_reviews_open', 'match_reviews', ['status'], unique=False, postgresql_where=sa.text("status = 'open'"))
    # Default thresholds (D-115, D-114). Editable in Settings later (REM-7).
    op.execute(
        """
        INSERT INTO app_settings (key, value) VALUES
          ('thank_you_days_first', '2'),
          ('thank_you_days_repeat', '7'),
          ('quarterly_days', '90'),
          ('import_cutoff_days', '60'),
          ('retention_basis', '"rolling"')
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_match_reviews_open', table_name='match_reviews', postgresql_where=sa.text("status = 'open'"))
    op.drop_table('match_reviews')
    op.drop_index('ix_interactions_donor_date', table_name='interactions')
    op.drop_table('interactions')
    op.drop_index('uq_messages_open_thank_you_per_gift', table_name='messages', postgresql_where=sa.text("kind = 'thank_you' AND status IN ('draft','approved')"))
    op.drop_index('uq_messages_open_per_donor_kind', table_name='messages', postgresql_where=sa.text("status IN ('draft','approved') AND kind <> 'thank_you'"))
    op.drop_index('ix_messages_donor', table_name='messages')
    op.drop_table('messages')
    op.drop_index('uq_import_rows_batch_row', table_name='import_rows')
    op.drop_index('ix_import_rows_row_key', table_name='import_rows')
    op.drop_table('import_rows')
    op.drop_index('uq_next_steps_one_open', table_name='next_steps', postgresql_where=sa.text("status = 'open'"))
    op.drop_table('next_steps')
    op.drop_table('message_templates')
    op.drop_table('digest_runs')
    op.drop_table('app_settings')
