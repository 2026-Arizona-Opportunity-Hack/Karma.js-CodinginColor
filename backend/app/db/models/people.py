"""People and access tables (DATA_MODEL 2.1)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TS = DateTime(timezone=True)


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(), primary_key=True)


def _created() -> Mapped[datetime]:
    return mapped_column(TS, server_default=func.now(), nullable=False)


class User(Base):
    """A board member (the super admin is a user too). Never hard-deleted."""

    __tablename__ = "users"

    id: Mapped[int] = _id()
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)
    last_assigned_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()
    deactivated_at: Mapped[datetime | None] = mapped_column(TS)


class Governance(Base):
    """Single row (id = 1): flat mode or one super admin (D-103)."""

    __tablename__ = "governance"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("super_admin_state IN ('none','active','dormant')", name="state"),
        CheckConstraint("reassign_scope IN ('anyone','own_only')", name="scope"),
        # 'none' exactly when there is no super admin user.
        CheckConstraint(
            "(super_admin_state = 'none') = (super_admin_user_id IS NULL)",
            name="state_matches_user",
        ),
        # own_only only makes sense while a super admin is active (GOV-4).
        CheckConstraint(
            "reassign_scope = 'anyone' OR super_admin_state = 'active'", name="scope_needs_admin"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, server_default=text("1"))
    super_admin_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    super_admin_state: Mapped[str] = mapped_column(
        Text, server_default=text("'none'"), nullable=False
    )
    reassign_scope: Mapped[str] = mapped_column(
        Text, server_default=text("'anyone'"), nullable=False
    )
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)


class SessionRow(Base):
    """A login session. Only SHA-256 hashes of the token and CSRF value are stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = _id()
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TS)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _created()
    last_used_at: Mapped[datetime | None] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    expires_at: Mapped[datetime | None] = mapped_column(TS)  # None = never expires


class AuditLog(Base):
    """Append-only record of who did what. No secrets, no message bodies (NFR-2)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor_kind IN ('user','api_key','cli','system')", name="actor_kind"),
    )

    id: Mapped[int] = _id()
    at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False, index=True)
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    ip: Mapped[str | None] = mapped_column(INET)
