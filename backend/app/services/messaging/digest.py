"""The reminder digest (REM-6, D-109).

The digest goes to board members only, never to donors, and only when a person clicks.
It carries counts, not donor names. In dry_run nothing is delivered and no network is used.
"""

import httpx
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.errors import Conflict
from app.repos import audit, digest
from app.schemas.common import MemberRef
from app.schemas.messages import DigestMember, DigestRunOut
from app.services import reminders
from app.services.messaging import mailer
from app.services.messaging.mailer import MailConfig


def _body(name: str, c: reminders.ReminderCounts) -> str:
    return (
        f"Hi {name},\n\nYour open reminders in CIC Compass:\n"
        f"- Thank-yous due: {c.thank_you_due}\n- Quarterly updates due: {c.quarterly_due}\n"
        f"- Next steps due: {c.next_step_due}\n"
        f"- Donors needing a new owner: {c.needs_reassignment}\n\n"
        "Open CIC Compass to act on them. Nothing is sent to donors without your approval."
    )


def send_digest(
    db: Session, clock: Clock, actor: Actor, *, cfg: MailConfig, client: httpx.Client
) -> DigestRunOut:
    digest.require_send(actor)
    if cfg.mode == "live" and not cfg.live_ready:
        raise Conflict("Live sending is not set up (mail key or sender missing). Nothing was sent.")
    counts = reminders.counts_by_member(db, actor, today(clock))
    people = digest.member_emails(db, list(counts))
    details: dict[str, dict[str, int | str]] = {}
    sent = 0
    for uid, c in counts.items():
        mine = {
            "thank_you_due": c.thank_you_due, "quarterly_due": c.quarterly_due,
            "next_step_due": c.next_step_due, "needs_reassignment": c.needs_reassignment,
        }  # fmt: skip
        # Needs-reassignment is the same org-wide number for everyone: not a reason to mail.
        if c.thank_you_due + c.quarterly_due + c.next_step_due == 0:
            details[str(uid)] = {**mine, "delivery": "skipped"}
            continue
        name, email = people[uid]
        delivery = "dry_run"
        if cfg.mode == "live":
            try:
                mailer.send_email(
                    client, cfg, to=email, subject="Your CIC Compass reminders", body=_body(name, c)
                )
                delivery = "sent"
            except mailer.MailError:  # one failure does not stop the others; no retry
                delivery = "failed"
        sent += delivery != "failed"
        details[str(uid)] = {**mine, "delivery": delivery}
    run = digest.insert_run(
        db, actor, mode=cfg.mode, recipients=sent, details=details, at=clock.now()
    )
    audit.write(
        db, actor, "digest.send", entity="digest_run", entity_id=run.id,
        data={"mode": cfg.mode, "recipients": sent},
    )  # fmt: skip
    return DigestRunOut(
        id=run.id, run_at=run.run_at, mode=cfg.mode,
        recipients=sent,
        members=[
            DigestMember(
                member=MemberRef(id=uid, display_name=people[uid][0]),
                **{k: v for k, v in details[str(uid)].items() if k != "delivery"},
            )
            for uid in counts
        ],
    )  # fmt: skip
