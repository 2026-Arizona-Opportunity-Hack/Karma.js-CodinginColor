"""Logging contacts and managing a donor's next step (DON-4, DON-9, DON-10).

Acting on a donor is allowed for the owner and an active super admin only (`donor.act`)."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import Donor, Interaction, NextStep
from app.errors import Conflict, Forbidden, NotFound


def _donor_to_act_on(db: Session, actor: Actor, donor_id: int) -> Donor:
    """Lock the donor row so two requests cannot both open a next step."""
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


def add_interaction(
    db: Session,
    actor: Actor,
    donor_id: int,
    *,
    kind: str,
    summary: str | None,
    occurred_on: date,
    at: datetime,
) -> Interaction:
    donor = _donor_to_act_on(db, actor, donor_id)
    row = Interaction(
        donor_id=donor.id,
        user_id=actor.user_id,
        kind=kind,
        occurred_on=occurred_on,
        summary=summary or None,
        created_at=at,
    )
    db.add(row)
    db.flush()
    return row


def set_next_step(
    db: Session, actor: Actor, donor_id: int, *, title: str, due_date: date, at: datetime
) -> NextStep:
    """One open step per donor: the current one is cancelled and kept as history."""
    donor = _donor_to_act_on(db, actor, donor_id)
    for old in db.execute(
        select(NextStep).where(NextStep.donor_id == donor.id, NextStep.status == "open")
    ).scalars():
        old.status = "cancelled"
    db.flush()  # free the one-open-step index before inserting
    step = NextStep(
        donor_id=donor.id, title=title, due_date=due_date, created_by=actor.user_id, created_at=at
    )
    db.add(step)
    db.flush()
    return step


def complete_next_step(
    db: Session, actor: Actor, step_id: int, *, today: date, at: datetime
) -> tuple[NextStep, Interaction]:
    """Mark done and log it on the timeline (DON-10)."""
    found = db.get(NextStep, step_id)
    if found is None:
        raise NotFound("Next step not found.")
    donor = _donor_to_act_on(db, actor, found.donor_id)
    step = db.execute(select(NextStep).where(NextStep.id == step_id).with_for_update()).scalar_one()
    if step.status != "open":
        raise Conflict(f"This next step is already {step.status}.")
    step.status = "done"
    step.done_at = at
    log = Interaction(
        donor_id=donor.id,
        user_id=actor.user_id,
        kind="note",
        occurred_on=today,
        summary=f"Completed next step: {step.title}",
        created_at=at,
    )
    db.add(log)
    db.flush()
    return step, log
