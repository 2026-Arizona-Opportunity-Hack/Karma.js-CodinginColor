"""Donor messages (MSG-2 to MSG-8). Acting on a message needs `donor.act` on its donor."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import Donor, Gift, Message, Program, User
from app.errors import Forbidden, NotFound

OPEN = ("draft", "approved")


def donor_to_act_on(db: Session, actor: Actor, donor_id: int) -> Donor:
    """Lock the donor row so two requests cannot both create the same draft."""
    donor = db.execute(
        select(Donor)
        .where(Donor.id == donor_id, Donor.deleted_at.is_(None), Donor.merged_into_id.is_(None))
        .with_for_update()
    ).scalar_one_or_none()
    if donor is None:
        raise NotFound("Donor not found.")
    if not can(actor, Action.DONOR_ACT, donor):
        raise Forbidden("Only the donor's owner can do this.")
    return donor


def gift_of(db: Session, donor_id: int, gift_id: int) -> tuple[Gift, str] | None:
    """A live gift of this donor with its program name, or None."""
    row = db.execute(
        select(Gift, Program.name)
        .join(Program, Program.id == Gift.program_id)
        .where(Gift.id == gift_id, Gift.donor_id == donor_id, Gift.deleted_at.is_(None))
    ).first()
    return None if row is None else (row[0], row[1])


def owner_name(db: Session, donor: Donor) -> str:
    if donor.owner_user_id is None:
        return ""
    user = db.get(User, donor.owner_user_id)
    return user.display_name if user else ""


def find_open(db: Session, donor_id: int, kind: str, gift_id: int | None) -> Message | None:
    """The open draft or approved message this request would duplicate (MSG-2)."""
    stmt = select(Message).where(Message.status.in_(OPEN), Message.kind == kind)
    stmt = (
        stmt.where(Message.gift_id == gift_id)
        if kind == "thank_you"
        else stmt.where(Message.donor_id == donor_id)
    )
    return db.execute(stmt).scalars().first()


def insert_draft(
    db: Session,
    actor: Actor,
    *,
    donor_id: int,
    gift_id: int | None,
    kind: str,
    channel: str,
    subject: str | None,
    body: str,
) -> tuple[Message, bool]:
    """Insert a draft; if the unique index says one is already open, return that one."""
    msg = Message(
        donor_id=donor_id, gift_id=gift_id, kind=kind, channel=channel, status="draft",
        subject=subject, body=body, created_by=actor.user_id,
    )  # fmt: skip
    try:
        with db.begin_nested():  # a savepoint, so the conflict does not abort the request
            db.add(msg)
            db.flush()
    except IntegrityError:
        existing = find_open(db, donor_id, kind, gift_id)
        if existing is None:
            raise
        return existing, False
    return msg, True


def list_for(db: Session, actor: Actor, status: str | None, limit: int = 200) -> list[Message]:
    """Messages of donors the actor may act on (owner, or active super admin)."""
    if actor.kind not in ("user", "cli"):
        raise Forbidden("Not allowed.")
    stmt = select(Message).join(Donor, Donor.id == Message.donor_id)
    if actor.kind != "cli" and not actor.is_active_super_admin:
        stmt = stmt.where(Donor.owner_user_id == actor.user_id)
    if status:
        stmt = stmt.where(Message.status == status)
    return list(
        db.execute(
            stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
        ).scalars()
    )


def donor_name(db: Session, donor_id: int) -> str:
    return db.execute(select(Donor.display_name).where(Donor.id == donor_id)).scalar_one()


def message_to_act_on(db: Session, actor: Actor, message_id: int) -> tuple[Message, Donor]:
    """Lock the message row, so two clicks on it cannot both move it (MSG-3)."""
    msg = db.execute(
        select(Message).where(Message.id == message_id).with_for_update()
    ).scalar_one_or_none()
    donor = db.get(Donor, msg.donor_id) if msg else None
    if msg is None or donor is None or donor.deleted_at is not None:
        raise NotFound("Message not found.")
    if not can(actor, Action.DONOR_ACT, donor):
        raise Forbidden("Only the donor's owner can do this.")
    return msg, donor
