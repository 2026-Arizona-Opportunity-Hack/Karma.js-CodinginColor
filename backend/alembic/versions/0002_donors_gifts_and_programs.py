"""donors gifts and programs

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14 16:53:49.012185

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")  # fuzzy donor search (DON-11)
    op.create_table('programs',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('slug', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_programs')),
    sa.UniqueConstraint('name', name=op.f('uq_programs_name')),
    sa.UniqueConstraint('slug', name=op.f('uq_programs_slug'))
    )
    op.create_table('donors',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=False),
    sa.Column('first_name', sa.Text(), nullable=True),
    sa.Column('last_name', sa.Text(), nullable=True),
    sa.Column('organization', sa.Text(), nullable=True),
    sa.Column('email', postgresql.CITEXT(), nullable=True),
    sa.Column('phone', sa.Text(), nullable=True),
    sa.Column('owner_user_id', sa.BigInteger(), nullable=True),
    sa.Column('owner_assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('do_not_contact', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_via', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('merged_into_id', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("created_via IN ('import','manual','merge')", name=op.f('ck_donors_created_via')),
    sa.CheckConstraint("kind IN ('person','organization','funder')", name=op.f('ck_donors_kind')),
    sa.CheckConstraint('merged_into_id IS NULL OR merged_into_id <> id', name=op.f('ck_donors_not_self_merged')),
    sa.ForeignKeyConstraint(['merged_into_id'], ['donors.id'], name=op.f('fk_donors_merged_into_id_donors')),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_donors_owner_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_donors'))
    )
    op.create_index('ix_donors_display_name_trgm', 'donors', ['display_name'], unique=False, postgresql_using='gin', postgresql_ops={'display_name': 'gin_trgm_ops'})
    op.create_index('ix_donors_owner_active', 'donors', ['owner_user_id'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_table('import_batches',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('file_sha256', sa.Text(), nullable=False),
    sa.Column('uploaded_by', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Text(), server_default=sa.text("'previewed'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('committed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reversed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cutoff_date', sa.Date(), nullable=True),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint("source IN ('spreadsheet','zeffy','benevity','generic')", name=op.f('ck_import_batches_source')),
    sa.CheckConstraint("status IN ('previewed','committed','reversed','expired')", name=op.f('ck_import_batches_status')),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name=op.f('fk_import_batches_uploaded_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_batches'))
    )
    op.create_index('uq_import_batches_committed_file', 'import_batches', ['source', 'file_sha256'], unique=True, postgresql_where=sa.text("status = 'committed'"))
    op.create_table('program_outcomes',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('program_id', sa.BigInteger(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('metric_label', sa.Text(), nullable=False),
    sa.Column('value', sa.Numeric(), nullable=False),
    sa.Column('unit', sa.Text(), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.CheckConstraint('period_end >= period_start', name=op.f('ck_program_outcomes_period')),
    sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name=op.f('fk_program_outcomes_program_id_programs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_program_outcomes'))
    )
    op.create_table('source_program_map',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('source_value_norm', sa.Text(), nullable=False),
    sa.Column('program_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name=op.f('fk_source_program_map_program_id_programs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_program_map')),
    sa.UniqueConstraint('source', 'source_value_norm', name=op.f('uq_source_program_map_source'))
    )
    op.create_table('donor_identities',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('donor_id', sa.BigInteger(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('value_norm', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('email','phone','zeffy_contact','benevity_donor','sheet_row','name_org')", name=op.f('ck_donor_identities_kind')),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], name=op.f('fk_donor_identities_donor_id_donors')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_donor_identities'))
    )
    op.create_index('ix_donor_identities_donor', 'donor_identities', ['donor_id'], unique=False)
    op.create_index('ix_donor_identities_name_org', 'donor_identities', ['value_norm'], unique=False, postgresql_where=sa.text("kind = 'name_org'"))
    op.create_index('uq_donor_identities_strong', 'donor_identities', ['kind', 'value_norm'], unique=True, postgresql_where=sa.text("kind <> 'name_org'"))
    op.create_table('gifts',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('donor_id', sa.BigInteger(), nullable=True),
    sa.Column('attribution', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('source_platform', sa.Text(), nullable=True),
    sa.Column('source_txn_id', sa.Text(), nullable=True),
    sa.Column('row_key', sa.Text(), nullable=False),
    sa.Column('gift_date', sa.Date(), nullable=False),
    sa.Column('gross_cents', sa.BigInteger(), nullable=False),
    sa.Column('fee_cents', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('net_cents', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.Text(), server_default=sa.text("'USD'"), nullable=False),
    sa.Column('program_id', sa.BigInteger(), nullable=False),
    sa.Column('campaign_name', sa.Text(), nullable=True),
    sa.Column('is_matching_gift', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('payer_name', sa.Text(), nullable=True),
    sa.Column('assumed_thanked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('import_batch_id', sa.BigInteger(), nullable=True),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(attribution = 'linked') = (donor_id IS NOT NULL)", name=op.f('ck_gifts_donor_iff_linked')),
    sa.CheckConstraint("attribution IN ('linked','anonymous','pending_review')", name=op.f('ck_gifts_attribution')),
    sa.CheckConstraint("currency = 'USD'", name=op.f('ck_gifts_usd_only')),
    sa.CheckConstraint("source IN ('zeffy','benevity','generic','manual')", name=op.f('ck_gifts_source')),
    sa.CheckConstraint('fee_cents >= 0 AND fee_cents <= gross_cents', name=op.f('ck_gifts_fee_range')),
    sa.CheckConstraint('gross_cents > 0', name=op.f('ck_gifts_gross_positive')),
    sa.CheckConstraint('net_cents = gross_cents - fee_cents', name=op.f('ck_gifts_net_matches')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_gifts_created_by_users')),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], name=op.f('fk_gifts_donor_id_donors')),
    sa.ForeignKeyConstraint(['import_batch_id'], ['import_batches.id'], name=op.f('fk_gifts_import_batch_id_import_batches')),
    sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name=op.f('fk_gifts_program_id_programs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_gifts'))
    )
    op.create_index('ix_gifts_batch', 'gifts', ['import_batch_id'], unique=False)
    op.create_index('ix_gifts_date', 'gifts', ['gift_date'], unique=False)
    op.create_index('ix_gifts_donor_date', 'gifts', ['donor_id', 'gift_date'], unique=False)
    op.create_index('uq_gifts_row_key_live', 'gifts', ['row_key'], unique=True, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_table('owner_history',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('donor_id', sa.BigInteger(), nullable=False),
    sa.Column('from_user_id', sa.BigInteger(), nullable=True),
    sa.Column('to_user_id', sa.BigInteger(), nullable=False),
    sa.Column('changed_by', sa.BigInteger(), nullable=True),
    sa.Column('method', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("method IN ('round_robin','manual','bulk','merge')", name=op.f('ck_owner_history_method')),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], name=op.f('fk_owner_history_changed_by_users')),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], name=op.f('fk_owner_history_donor_id_donors')),
    sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], name=op.f('fk_owner_history_from_user_id_users')),
    sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], name=op.f('fk_owner_history_to_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_owner_history'))
    )
    op.create_index('ix_owner_history_donor', 'owner_history', ['donor_id', 'changed_at'], unique=False)
    # Seed programs (SRS section 8). General is the fallback for unmapped campaigns (ING-7).
    op.execute(
        """
        INSERT INTO programs (name, slug) VALUES
          ('AI Academy', 'ai-academy'),
          ('K12 Program', 'k12-program'),
          ('Summer Camp', 'summer-camp'),
          ('Day of Compute', 'day-of-compute'),
          ('General', 'general')
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_owner_history_donor', table_name='owner_history')
    op.drop_table('owner_history')
    op.drop_index('uq_gifts_row_key_live', table_name='gifts', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index('ix_gifts_donor_date', table_name='gifts')
    op.drop_index('ix_gifts_date', table_name='gifts')
    op.drop_index('ix_gifts_batch', table_name='gifts')
    op.drop_table('gifts')
    op.drop_index('uq_donor_identities_strong', table_name='donor_identities', postgresql_where=sa.text("kind <> 'name_org'"))
    op.drop_index('ix_donor_identities_name_org', table_name='donor_identities', postgresql_where=sa.text("kind = 'name_org'"))
    op.drop_index('ix_donor_identities_donor', table_name='donor_identities')
    op.drop_table('donor_identities')
    op.drop_table('source_program_map')
    op.drop_table('program_outcomes')
    op.drop_index('uq_import_batches_committed_file', table_name='import_batches', postgresql_where=sa.text("status = 'committed'"))
    op.drop_table('import_batches')
    op.drop_index('ix_donors_owner_active', table_name='donors', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index('ix_donors_display_name_trgm', table_name='donors', postgresql_using='gin', postgresql_ops={'display_name': 'gin_trgm_ops'})
    op.drop_table('donors')
    op.drop_table('programs')
