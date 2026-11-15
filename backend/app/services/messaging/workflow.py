"""Edit, approve and cancel (MSG-3, MSG-4). Sending is in send.py.

draft -> approved -> sent | sent_manually | failed, and draft or approved -> cancelled. The
same rules are enforced again by CHECK constraints (approved needs an approver and a hash;
sent needs an approver and times), so a bug here cannot send an unapproved message.
"""

import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import Donor, Message
from app.errors import Conflict, Invalid
from app.repos import audit, messages
from app.schemas.messages import MessageOut, MessageUpdate
from app.services.messaging import defaults
from app.services.messaging.service import to_out


def content_hash(subject: str | None, body: str) -> str:
    """What approval covers: the subject and the body together (MSG-4)."""
    return hashlib.sha256(f"{subject or ''}\x00{body}".encode()).hexdigest()


def _conflict(msg: Message, action: str) -> Conflict:
    return Conflict(f"A message that is {msg.status} cannot be {action}.")


def edit(db: Session, actor: Actor, message_id: int, body: MessageUpdate) -> MessageOut:
    msg, _ = messages.message_to_act_on(db, actor, message_id)
    if msg.status not in ("draft", "approved"):
        raise _conflict(msg, "edited")
    if body.subject is None and body.body is None:
        raise Invalid("Send a new subject or body.")
    was_approved = msg.status == "approved"
    if body.body is not None:
        msg.body = body.body
    if body.subject is not None and msg.channel == "email":
        msg.subject = body.subject
    # Any edit voids the approval: a person must approve the new words (MSG-3).
    msg.status = "draft"
    msg.approved_by = msg.approved_at = msg.body_sha256_at_approval = None
    db.flush()
    audit.write(
        db, actor, "message.edit", entity="message", entity_id=msg.id,
        data={"donor_id": msg.donor_id, "approval_cleared": was_approved},
    )  # fmt: skip
    return to_out(db, msg)


def check_reachable(msg: Message, donor: Donor) -> None:
    if donor.do_not_contact:
        raise Conflict("This donor is marked do not contact.")
    if msg.channel == "email" and not donor.email:
        raise Invalid("This donor has no email address on file.")
    if msg.channel == "sms" and not donor.phone:
        raise Invalid("This donor has no phone number on file.")


def approve(db: Session, actor: Actor, message_id: int, *, at: datetime) -> MessageOut:
    msg, donor = messages.message_to_act_on(db, actor, message_id)
    if msg.status != "draft":
        raise _conflict(msg, "approved")
    if defaults.EDIT_MARKER in msg.body or defaults.EDIT_MARKER in (msg.subject or ""):
        raise Invalid("Replace the [EDIT: ...] text with your own words before approving.")
    check_reachable(msg, donor)
    msg.status = "approved"
    msg.approved_by = actor.user_id
    msg.approved_at = at
    msg.body_sha256_at_approval = content_hash(msg.subject, msg.body)
    db.flush()
    audit.write(
        db, actor, "message.approve", entity="message", entity_id=msg.id,
        data={"donor_id": msg.donor_id, "kind": msg.kind, "channel": msg.channel},
    )  # fmt: skip
    return to_out(db, msg)


def cancel(db: Session, actor: Actor, message_id: int) -> MessageOut:
    msg, _ = messages.message_to_act_on(db, actor, message_id)
    if msg.status not in ("draft", "approved"):
        raise _conflict(msg, "cancelled")
    msg.status = "cancelled"
    msg.approved_by = msg.approved_at = msg.body_sha256_at_approval = None
    db.flush()
    audit.write(
        db, actor, "message.cancel", entity="message", entity_id=msg.id,
        data={"donor_id": msg.donor_id},
    )  # fmt: skip
    return to_out(db, msg)
