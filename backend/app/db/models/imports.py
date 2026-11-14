"""Import rows and identity-review items (DATA_MODEL 2.4)."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TS, id_col


class ImportRow(Base):
    """One parsed file row and what we decided about it. `raw` is dropped 30 days after commit."""

    __tablename__ = "import_rows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new','already_imported','needs_review','invalid',"
            "'donor_new','donor_matched')",
            name="status",
        ),
        # Every invalid row carries its reason: nothing is dropped silently (ING-6).
        CheckConstraint("status <> 'invalid' OR reason IS NOT NULL", name="invalid_has_reason"),
        Index("uq_import_rows_batch_row", "batch_id", "row_number", unique=True),
        Index("ix_import_rows_row_key", "row_key"),
    )

    id: Mapped[int] = id_col()
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    normalized: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    row_key: Mapped[str | None] = mapped_column(Text)
    gift_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gifts.id"))
    donor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("donors.id"))


class MatchReview(Base):
    """A possible duplicate a person must decide on (DED-3, DED-4)."""

    __tablename__ = "match_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('open','linked','created_new','anonymous')", name="status"),
        # Open exactly while undecided; decisions record who and when (DED-4, NFR-2).
        CheckConstraint(
            "(status = 'open') = (decided_at IS NULL AND decided_by IS NULL)",
            name="decision_recorded",
        ),
        Index("ix_match_reviews_open", "status", postgresql_where=text("status = 'open'")),
    )

    id: Mapped[int] = id_col()
    import_row_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("import_rows.id"))
    gift_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gifts.id"))
    incoming: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    candidate_donor_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), server_default=text("'{}'"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"), nullable=False)
    decided_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(TS)
