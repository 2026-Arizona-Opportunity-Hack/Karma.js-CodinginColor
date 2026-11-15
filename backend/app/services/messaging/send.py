"""Send an approved email, or record a text sent by hand (MSG-3 to MSG-7).

Only `approved` can be sent. The message row is locked first, so two simultaneous sends
produce one send. The hash stored at approval must still match the words (MSG-4). Every
send writes the message record, a timeline interaction (so reminders clear) and an audit
entry without the words.
"""

from datetime import date, datetime

import httpx
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.db.models import Donor, Interaction, Message
from app.errors import Conflict, Invalid
from app.repos import audit, messages
from app.schemas.messages import MessageOut
from app.services.messaging import mailer
from app.services.messaging.mailer import MailConfig
from app.services.messaging.service import to_out
from app.services.messaging.workflow import check_reachable, content_hash


def _locked_approved(db: Session, actor: Actor, message_id: int) -> tuple[Message, Donor]:
    msg, donor = messages.message_to_act_on(db, actor, message_id)
    if msg.status != "approved":
        raise Conflict(f"A message that is {msg.status} cannot be sent. Only approved ones can.")
    if msg.approved_by is None or msg.body_sha256_at_approval is None:
        raise Conflict("This message has no approval on record.")
    if content_hash(msg.subject, msg.body) != msg.body_sha256_at_approval:
        raise Conflict("The words changed after approval. It was not sent; approve it again.")
    check_reachable(msg, donor)
    return msg, donor


def _record(db: Session, actor: Actor, msg: Message, *, day: date, at: datetime, mode: str) -> None:
    """The timeline entry that clears the reminder, and the audit entry (MSG-7)."""
    label = "Thank-you" if msg.kind == "thank_you" else "Update"
    how = {"manual": "text sent from the owner's phone", "dry_run": "email (dry run)"}.get(
        mode, "email"
    )
    db.add(
        Interaction(
            donor_id=msg.donor_id, user_id=actor.user_id,
            kind="thank_you" if msg.kind == "thank_you" else "update",
            occurred_on=day, summary=f"{label} {how}", message_id=msg.id, gift_id=msg.gift_id,
        )
    )  # fmt: skip
    audit.write(
        db, actor, "message.send", entity="message", entity_id=msg.id, at=at,
        data={
            "donor_id": msg.donor_id, "kind": msg.kind, "channel": msg.channel,
            "mode": mode, "provider_ref": msg.provider_ref,
        },
    )  # fmt: skip


def send_email(
    db: Session, clock: Clock, actor: Actor, message_id: int, *, cfg: MailConfig,
    client: httpx.Client,
) -> MessageOut:  # fmt: skip
    msg, donor = _locked_approved(db, actor, message_id)
    if msg.channel != "email":
        raise Invalid("Texts are sent from your own phone. Open the text link, then Mark sent.")
    if cfg.mode == "live" and not cfg.live_ready:
        raise Conflict("Live sending is not set up (mail key or sender missing). Nothing was sent.")
    at = clock.now()
    msg.sent_by, msg.sent_at, msg.delivery_mode = actor.user_id, at, cfg.mode
    if cfg.mode == "dry_run":
        msg.provider_ref = f"dry-run-{msg.id}"  # recorded, delivered nowhere; no client use
    else:
        assert donor.email is not None  # check_reachable
        try:
            msg.provider_ref = mailer.send_email(
                client, cfg, to=donor.email, subject=msg.subject or "", body=msg.body
            )
        except mailer.MailError as exc:  # a failed send is final: no retry (MSG-7)
            msg.status, msg.error, msg.sent_by, msg.sent_at = "failed", str(exc), None, None
            db.flush()
            audit.write(
                db, actor, "message.send_failed", entity="message", entity_id=msg.id,
                data={"donor_id": msg.donor_id, "channel": "email", "mode": "live"},
            )  # fmt: skip
            return to_out(db, msg)
    msg.status = "sent"
    db.flush()
    _record(db, actor, msg, day=today(clock), at=at, mode=cfg.mode)
    return to_out(db, msg)


def mark_sent(db: Session, clock: Clock, actor: Actor, message_id: int) -> MessageOut:
    """A text the owner sent from their own phone (MSG-5)."""
    msg, _ = _locked_approved(db, actor, message_id)
    if msg.channel != "sms":
        raise Invalid("Only a text is marked sent by hand. Emails are sent with Send.")
    at = clock.now()
    msg.status, msg.sent_by, msg.sent_at, msg.delivery_mode = (
        "sent_manually", actor.user_id, at, "manual",
    )  # fmt: skip
    db.flush()
    _record(db, actor, msg, day=today(clock), at=at, mode="manual")
    return to_out(db, msg)
