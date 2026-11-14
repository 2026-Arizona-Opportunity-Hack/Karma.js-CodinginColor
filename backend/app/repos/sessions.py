"""Login sessions. Tokens are looked up by SHA-256 hash; raw tokens never hit the DB."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import SessionRow


def create(
    db: Session,
    *,
    user_id: int,
    token_hash: str,
    csrf_hash: str,
    now: datetime,
    expires_at: datetime,
    ip: str | None,
    user_agent: str | None,
) -> SessionRow:
    row = SessionRow(
        user_id=user_id,
        token_hash=token_hash,
        csrf_hash=csrf_hash,
        created_at=now,
        last_seen_at=now,
        expires_at=expires_at,
        ip=ip,
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(row)
    db.flush()
    return row


def find_live(db: Session, token_hash: str) -> SessionRow | None:
    stmt = select(SessionRow).where(
        SessionRow.token_hash == token_hash, SessionRow.revoked_at.is_(None)
    )
    return db.execute(stmt).scalar_one_or_none()


def revoke(db: Session, row: SessionRow, now: datetime) -> None:
    row.revoked_at = now


def revoke_all_for_user(db: Session, user_id: int, now: datetime) -> None:
    db.execute(
        update(SessionRow)
        .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
        .values(revoked_at=now)
    )
