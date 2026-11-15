"""Digest runs (REM-6): one row per click, counts only, never donor names (D-109)."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import DigestRun, User
from app.errors import Forbidden


def require_send(actor: Actor) -> None:
    if not can(actor, Action.DIGEST_SEND) or actor.user_id is None:
        raise Forbidden("Only a super admin can send the digest while one is active.")


def member_emails(db: Session, user_ids: list[int]) -> dict[int, tuple[str, str]]:
    """{user id: (display name, email)} for board members only."""
    rows = db.query(User.id, User.display_name, User.email).filter(User.id.in_(user_ids)).all()
    return {r.id: (r.display_name, str(r.email)) for r in rows}


def insert_run(
    db: Session, actor: Actor, *, mode: str, recipients: int, details: dict[str, Any], at: datetime
) -> DigestRun:
    require_send(actor)
    run = DigestRun(
        triggered_by=actor.user_id, mode=mode, recipients=recipients, details=details, run_at=at
    )
    db.add(run)
    db.flush()
    return run
