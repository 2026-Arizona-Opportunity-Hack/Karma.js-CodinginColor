"""Audit log writer. Append-only: there is no update or delete here (NFR-2)."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import AuditLog


def write(
    db: Session,
    actor: Actor,
    action: str,
    *,
    entity: str | None = None,
    entity_id: int | None = None,
    data: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> None:
    row = AuditLog(
        actor_kind=actor.kind,
        actor_id=actor.id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        data=data or {},
        ip=actor.ip,
    )
    if at is not None:
        row.at = at
    db.add(row)


def count_failed_logins(db: Session, *, email: str, ip: str | None, since: datetime) -> int:
    """Failed logins since `since` matching this email or this IP (AUTH-6)."""
    match = AuditLog.data["email"].astext == email.lower()
    if ip:
        match = or_(match, AuditLog.ip == ip)
    stmt = (
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "auth.login_failed", AuditLog.at >= since, match)
    )
    return db.execute(stmt).scalar_one()
