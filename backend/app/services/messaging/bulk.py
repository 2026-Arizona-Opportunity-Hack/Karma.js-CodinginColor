"""Draft a quarterly update for each donor I owe one (MSG-2). Idempotent."""

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.db.models import Donor
from app.schemas.messages import DraftBatchOut, MessageCreate
from app.services import reminders
from app.services.messaging import service


def draft_quarterly(db: Session, clock: Clock, actor: Actor) -> DraftBatchOut:
    made, existing, out = 0, 0, []
    for r in reminders.quarterly_due_for(db, actor, today(clock), actor.user_id or 0):
        donor = db.get(Donor, r.donor_id)
        channel = "email" if donor and donor.email else "sms" if donor and donor.phone else None
        if channel is None:
            continue  # nobody to write to
        msg, created = service.create_draft(
            db, actor, r.donor_id, MessageCreate(kind="quarterly_update", channel=channel)
        )
        made, existing = made + created, existing + (not created)
        out.append(msg)
    return DraftBatchOut(created=made, skipped_existing=existing, messages=out)
