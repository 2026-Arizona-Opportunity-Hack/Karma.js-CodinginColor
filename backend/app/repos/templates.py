"""Message templates (MSG-1). Editing needs `templates.manage` (GOV-4)."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import MessageTemplate
from app.errors import Forbidden
from app.services.messaging import defaults


def _require_manage(actor: Actor) -> None:
    if not can(actor, Action.TEMPLATES_MANAGE):
        raise Forbidden("Only a super admin can edit templates while one is active.")


def _ensure(db: Session, kind: str, channel: str) -> MessageTemplate:
    """The stored row, created from the built-in text on first use. Never overwrites."""
    subject, body = defaults.DEFAULTS[(kind, channel)]
    db.execute(
        insert(MessageTemplate)
        .values(kind=kind, channel=channel, subject=subject, body=body)
        .on_conflict_do_nothing(index_elements=["kind", "channel"])
    )
    return db.execute(
        select(MessageTemplate).where(
            MessageTemplate.kind == kind, MessageTemplate.channel == channel
        )
    ).scalar_one()


def get_for_draft(db: Session, kind: str, channel: str) -> MessageTemplate:
    """Used when a person who may act on a donor drafts a message. No template permission."""
    return _ensure(db, kind, channel)


def list_all(db: Session, actor: Actor) -> list[MessageTemplate]:
    _require_manage(actor)
    return [_ensure(db, k, c) for k in defaults.TEMPLATE_KINDS for c in ("email", "sms")]


def upsert(
    db: Session, actor: Actor, *, kind: str, channel: str, subject: str | None, body: str
) -> MessageTemplate:
    _require_manage(actor)
    row = _ensure(db, kind, channel)
    row.subject = subject if channel == "email" else None
    row.body = body
    row.updated_by = actor.user_id
    row.updated_at = func.now()
    db.flush()
    db.refresh(row)  # updated_at is set by the database
    return row
