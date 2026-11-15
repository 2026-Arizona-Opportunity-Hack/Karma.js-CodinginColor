"""Assign a newly created donor inside the caller's transaction."""

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.db.models import Donor
from app.repos import ownership


def assign_new(
    db: Session,
    actor: Actor,
    donor: Donor,
    clock: Clock,
    *,
    action: ownership.AssignmentAction = "import.run",
) -> None:
    ownership.assign(db, actor, donor, clock.now(), action=action)
