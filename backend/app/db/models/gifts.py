"""Programs, gifts and import batches (DATA_MODEL 2.3 and 2.4). Money is integer cents."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TS, created_col, id_col


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = id_col()
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)


class SourceProgramMap(Base):
    """Maps a platform's campaign text to a program (ING-7)."""

    __tablename__ = "source_program_map"
    __table_args__ = (UniqueConstraint("source", "source_value_norm"),)

    id: Mapped[int] = id_col()
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_value_norm: Mapped[str] = mapped_column(Text, nullable=False)
    program_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("programs.id"), nullable=False)


class ProgramOutcome(Base):
    """Hand-entered outcomes for the funder export (RPT-3)."""

    __tablename__ = "program_outcomes"
    __table_args__ = (CheckConstraint("period_end >= period_start", name="period"),)

    id: Mapped[int] = id_col()
    program_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("programs.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    metric_label: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint("source IN ('spreadsheet','zeffy','benevity','generic')", name="source"),
        CheckConstraint("status IN ('previewed','committed','reversed','expired')", name="status"),
        # The same file cannot be committed twice for a source (DED-1).
        Index(
            "uq_import_batches_committed_file",
            "source",
            "file_sha256",
            unique=True,
            postgresql_where=text("status = 'committed'"),
        ),
    )

    id: Mapped[int] = id_col()
    source: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'previewed'"), nullable=False)
    created_at: Mapped[datetime] = created_col()
    committed_at: Mapped[datetime | None] = mapped_column(TS)
    reversed_at: Mapped[datetime | None] = mapped_column(TS)
    cutoff_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # counts and cents per class


class Gift(Base):
    __tablename__ = "gifts"
    __table_args__ = (
        CheckConstraint(
            "attribution IN ('linked','anonymous','pending_review')", name="attribution"
        ),
        CheckConstraint("source IN ('zeffy','benevity','generic','manual')", name="source"),
        CheckConstraint("gross_cents > 0", name="gross_positive"),
        CheckConstraint("fee_cents >= 0 AND fee_cents <= gross_cents", name="fee_range"),
        CheckConstraint("net_cents = gross_cents - fee_cents", name="net_matches"),
        CheckConstraint("currency = 'USD'", name="usd_only"),
        # A donor id exists exactly when the gift is linked (DED-5, DED-8).
        CheckConstraint(
            "(attribution = 'linked') = (donor_id IS NOT NULL)", name="donor_iff_linked"
        ),
        # Re-import never inserts the same gift twice (DED-2).
        Index(
            "uq_gifts_row_key_live",
            "row_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_gifts_donor_date", "donor_id", "gift_date"),
        Index("ix_gifts_date", "gift_date"),
        Index("ix_gifts_batch", "import_batch_id"),
    )

    id: Mapped[int] = id_col()
    donor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("donors.id"))
    attribution: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_platform: Mapped[str | None] = mapped_column(Text)  # generic: azgives, united_way, ...
    source_txn_id: Mapped[str | None] = mapped_column(Text)
    row_key: Mapped[str] = mapped_column(Text, nullable=False)
    gift_date: Mapped[date] = mapped_column(Date, nullable=False)
    gross_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_cents: Mapped[int] = mapped_column(BigInteger, server_default=text("0"), nullable=False)
    net_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(Text, server_default=text("'USD'"), nullable=False)
    program_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("programs.id"), nullable=False)
    campaign_name: Mapped[str | None] = mapped_column(Text)  # raw value used for mapping
    is_matching_gift: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    payer_name: Mapped[str | None] = mapped_column(Text)  # e.g. employer for Benevity
    assumed_thanked: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    import_batch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("import_batches.id"))
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_col()
    deleted_at: Mapped[datetime | None] = mapped_column(TS)
