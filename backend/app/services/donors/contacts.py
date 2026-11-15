"""Log a contact, set and complete a next step."""

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.db.models import Interaction, NextStep
from app.errors import Invalid
from app.repos import relationship as repo
from app.repos import users
from app.schemas.common import MemberRef
from app.schemas.donors import InteractionCreate, InteractionOut, NextStepIn, NextStepOut


def _step(step: NextStep) -> NextStepOut:
    return NextStepOut(
        id=step.id,
        donor_id=step.donor_id,
        title=step.title,
        due_date=step.due_date,
        status=step.status,
        done_at=step.done_at,
    )


def _interaction(db: Session, row: Interaction) -> InteractionOut:
    user = users.get_for_session(db, row.user_id) if row.user_id is not None else None
    return InteractionOut(
        id=row.id,
        donor_id=row.donor_id,
        kind=row.kind,
        occurred_on=row.occurred_on,
        summary=row.summary,
        user=MemberRef(id=user.id, display_name=user.display_name, is_active=user.is_active)
        if user
        else None,
    )


def log_interaction(
    db: Session, clock: Clock, actor: Actor, donor_id: int, body: InteractionCreate
) -> InteractionOut:
    day = today(clock)
    occurred_on = body.occurred_on or day
    if occurred_on > day:
        raise Invalid("A contact cannot be dated in the future.")
    row = repo.add_interaction(
        db, actor, donor_id, kind=body.kind, summary=body.summary, occurred_on=occurred_on
    )
    return _interaction(db, row)


def set_next_step(db: Session, actor: Actor, donor_id: int, body: NextStepIn) -> NextStepOut:
    return _step(repo.set_next_step(db, actor, donor_id, title=body.title, due_date=body.due_date))


def complete_next_step(db: Session, clock: Clock, actor: Actor, step_id: int) -> NextStepOut:
    step, _ = repo.complete_next_step(db, actor, step_id, today=today(clock), at=clock.now())
    return _step(step)
