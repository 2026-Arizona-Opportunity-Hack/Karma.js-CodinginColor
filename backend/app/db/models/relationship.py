"""Relationship work: contacts, next steps, messages and settings (DATA_MODEL 2.5)."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TS, created_col, id_col

MESSAGE_KINDS = "('thank_you','quarterly_update','lapsed_nudge','event_invite')"


class MessageTemplate(Base):
    __tablename__ = "message_templates"
    __table_args__ = (
        CheckConstraint(f"kind IN {MESSAGE_KINDS}", name="kind"),
        CheckConstraint("channel IN ('email','sms')", name="channel"),
        UniqueConstraint("kind", "channel"),
    )

    id: Mapped[int] = id_col()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)


class Message(Base):
    """A donor message. Only a person moves it draft -> approved -> sent (MSG-3, MSG-4).

    The CHECK constraints make a send without approval impossible even if code is wrong.
    """

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(f"kind IN {MESSAGE_KINDS}", name="kind"),
        CheckConstraint("channel IN ('email','sms')", name="channel"),
        CheckConstraint(
            "status IN ('draft','approved','sent','sent_manually','cancelled','failed')",
            name="status",
        ),
        CheckConstraint(
            "delivery_mode IS NULL OR delivery_mode IN ('dry_run','live','manual')",
            name="delivery_mode",
        ),
        CheckConstraint(
            "status NOT IN ('sent','sent_manually') OR "
            "(approved_by IS NOT NULL AND approved_at IS NOT NULL AND sent_at IS NOT NULL)",
            name="sent_was_approved",
        ),
        CheckConstraint(
            "status <> 'approved' OR "
            "(approved_by IS NOT NULL AND body_sha256_at_approval IS NOT NULL)",
            name="approved_has_approver",
        ),
        # Never two open drafts of one kind for a donor (MSG-2); one open thank-you per gift.
        Index(
            "uq_messages_open_per_donor_kind",
            "donor_id",
            "kind",
            unique=True,
            postgresql_where=text("status IN ('draft','approved') AND kind <> 'thank_you'"),
        ),
        Index(
            "uq_messages_open_thank_you_per_gift",
            "gift_id",
            unique=True,
            postgresql_where=text("kind = 'thank_you' AND status IN ('draft','approved')"),
        ),
        Index("ix_messages_donor", "donor_id", "created_at"),
    )

    id: Mapped[int] = id_col()
    donor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("donors.id"), nullable=False)
    gift_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gifts.id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"), nullable=False)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_sha256_at_approval: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    sent_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_col()
    approved_at: Mapped[datetime | None] = mapped_column(TS)
    sent_at: Mapped[datetime | None] = mapped_column(TS)
    delivery_mode: Mapped[str | None] = mapped_column(Text)
    provider_ref: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class Interaction(Base):
    """A timeline entry: a logged contact, note, thank-you or system event (DON-6, DON-9)."""

    __tablename__ = "interactions"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('call','text','email','meeting','note','thank_you','update','system')",
            name="kind",
        ),
        Index("ix_interactions_donor_date", "donor_id", "occurred_on"),
    )

    id: Mapped[int] = id_col()
    donor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("donors.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))  # null = system
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("messages.id"))
    gift_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gifts.id"))
    created_at: Mapped[datetime] = created_col()


class NextStep(Base):
    __tablename__ = "next_steps"
    __table_args__ = (
        CheckConstraint("status IN ('open','done','cancelled')", name="status"),
        CheckConstraint("(status = 'done') = (done_at IS NOT NULL)", name="done_at_matches"),
        # One open next step per donor (DON-10).
        Index(
            "uq_next_steps_one_open",
            "donor_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = id_col()
    donor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("donors.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created_col()
    done_at: Mapped[datetime | None] = mapped_column(TS)


class DigestRun(Base):
    """One click of "Send reminder digest" (REM-6). Counts only, no donor data."""

    __tablename__ = "digest_runs"
    __table_args__ = (CheckConstraint("mode IN ('dry_run','live')", name="mode"),)

    id: Mapped[int] = id_col()
    triggered_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    run_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    recipients: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )


class AppSetting(Base):
    """Editable thresholds (REM-7). Defaults are seeded by the migration."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
