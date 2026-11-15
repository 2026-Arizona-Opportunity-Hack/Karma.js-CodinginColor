"""Lapsed-donor radar (SRS 3.2 item 1, D-117): donors in the retention "lapsed" class, listed per
owner, each with a drafted nudge. Classes come from lane C's retention query unchanged (RPT-2,
D-127). Do-not-contact donors are left out (MSG-8). Drafts go through the messaging service, so
they are idempotent (MSG-2) and only the owner or an active super admin can create them; a human
approves and sends every one."""

from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.repos import lapsed as repo
from app.schemas.messages import DraftBatchOut, MessageCreate
from app.schemas.reports import RetentionDonor
from app.services.messaging import service as messaging
from app.services.reports import retention


class LapsedDonor(BaseModel):
    donor_id: int
    display_name: str
    cents_prev: int
    last_gift_date: date | None
    can_draft: bool
    draft_message_id: int | None


class LapsedOwner(BaseModel):
    owner_user_id: int | None
    owner_name: str
    donors: list[LapsedDonor]


class LapsedReport(BaseModel):
    as_of: date
    owners: list[LapsedOwner]
    total: int


def _lapsed(db: Session, actor: Actor, as_of: date) -> list[tuple[RetentionDonor, dict[str, Any]]]:
    found = retention.build(db, actor, as_of=as_of, basis="rolling").donors["lapsed"]
    facts = repo.facts(db, actor, [d.donor_id for d in found])
    return [(d, facts[d.donor_id]) for d in found if not facts[d.donor_id]["do_not_contact"]]


def build(db: Session, actor: Actor, *, as_of: date) -> LapsedReport:
    groups: dict[int | None, LapsedOwner] = {}
    for d, f in _lapsed(db, actor, as_of):
        owner = groups.setdefault(
            f["owner_user_id"],
            LapsedOwner(
                owner_user_id=f["owner_user_id"],
                owner_name=f["owner_name"] or "Unassigned",
                donors=[],
            ),
        )
        owner.donors.append(
            LapsedDonor(
                donor_id=d.donor_id,
                display_name=d.display_name,
                cents_prev=d.cents_prev,
                last_gift_date=f["last_gift"],
                can_draft=bool(f["reachable"]) and f["owner_user_id"] is not None,
                draft_message_id=f["draft_id"],
            )
        )
    owners = sorted(groups.values(), key=lambda o: (o.owner_user_id is None, o.owner_name.lower()))
    return LapsedReport(as_of=as_of, owners=owners, total=sum(len(o.donors) for o in owners))


def draft_mine(db: Session, clock: Clock, actor: Actor) -> DraftBatchOut:
    """A lapsed-nudge draft for each of my lapsed donors who has an email or phone."""
    made, existing, out = 0, 0, []
    for d, f in _lapsed(db, actor, today(clock)):
        if f["owner_user_id"] != actor.user_id or not f["reachable"]:
            continue
        msg, created = messaging.create_draft(
            db, actor, d.donor_id,
            MessageCreate(kind="lapsed_nudge", channel="email" if f["has_email"] else "sms"),
        )  # fmt: skip
        made, existing = made + created, existing + (not created)
        out.append(msg)
    return DraftBatchOut(created=made, skipped_existing=existing, messages=out)
