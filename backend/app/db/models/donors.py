"""Donors, how we recognise them, and ownership history (DATA_MODEL 2.2)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TS, created_col, id_col


class Donor(Base):
    """A person, organization or funder. Soft-deleted only; ownership lives here (OWN-1)."""

    __tablename__ = "donors"
    __table_args__ = (
        CheckConstraint("kind IN ('person','organization','funder')", name="kind"),
        CheckConstraint("created_via IN ('import','manual','merge')", name="created_via"),
        CheckConstraint("merged_into_id IS NULL OR merged_into_id <> id", name="not_self_merged"),
        Index(
            "ix_donors_owner_active",
            "owner_user_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_donors_custom", "custom", postgresql_using="gin"),
        Index(
            "ix_donors_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = id_col()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT)  # contact detail (DON-3)
    phone: Mapped[str | None] = mapped_column(Text)  # contact detail (DON-3)
    # Null only while the donor waits for identity review (DED-5).
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    owner_assigned_at: Mapped[datetime | None] = mapped_column(TS)
    do_not_contact: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # Values of custom fields, keyed by field_definitions.key (CUS-1).
    custom: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_via: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = mapped_column(
        TS, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TS)
    merged_into_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("donors.id"))


class DonorIdentity(Base):
    """How a donor is recognised across sources (DED-3). name_org is only a review hint."""

    __tablename__ = "donor_identities"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('email','phone','zeffy_contact','benevity_donor','sheet_row','name_org')",
            name="kind",
        ),
        # One donor per strong identity; name_org may repeat.
        Index(
            "uq_donor_identities_strong",
            "kind",
            "value_norm",
            unique=True,
            postgresql_where=text("kind <> 'name_org'"),
        ),
        Index("ix_donor_identities_donor", "donor_id"),
        Index(
            "ix_donor_identities_name_org", "value_norm", postgresql_where=text("kind = 'name_org'")
        ),
    )

    id: Mapped[int] = id_col()
    donor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("donors.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value_norm: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_col()


class OwnerHistory(Base):
    """Every ownership change: who, from whom, how, why (OWN-4). Append-only."""

    __tablename__ = "owner_history"
    __table_args__ = (
        CheckConstraint("method IN ('round_robin','manual','bulk','merge')", name="method"),
        Index("ix_owner_history_donor", "donor_id", "changed_at"),
    )

    id: Mapped[int] = id_col()
    donor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("donors.id"), nullable=False)
    from_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    to_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )  # null = system
    method: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
