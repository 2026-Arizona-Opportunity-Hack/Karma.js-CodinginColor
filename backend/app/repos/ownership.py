"""Round-robin SQL, serialized with imports and review decisions (DATA_MODEL 3.3)."""

from datetime import datetime
from typing import Literal

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.authz import policy
from app.authz.actor import Actor
from app.db.models import Donor, OwnerHistory, User
from app.errors import Conflict, Forbidden
from app.repos import audit

AssignmentAction = Literal["import.run", "review.decide"]


def lock(db: Session, actor: Actor, *, action: AssignmentAction = "import.run") -> None:
    if not policy.can(actor, action):
        raise Forbidden("You cannot assign imported donors.")
    db.execute(text("SELECT pg_advisory_xact_lock(4201)"))


def assign(
    db: Session,
    actor: Actor,
    donor: Donor,
    at: datetime,
    *,
    action: AssignmentAction = "import.run",
) -> None:
    lock(db, actor, action=action)
    if donor.owner_user_id is not None:
        return  # new gifts and review links never change existing ownership
    user = db.scalar(
        select(User)
        .outerjoin(Donor, and_(Donor.owner_user_id == User.id, Donor.deleted_at.is_(None)))
        .where(User.is_active.is_(True))
        .group_by(User.id)
        .order_by(func.count(Donor.id), User.last_assigned_at.asc().nulls_first(), User.id)
        .limit(1)
    )
    if user is None:
        raise Conflict("No active board member is available to own this donor.")
    donor.owner_user_id, donor.owner_assigned_at = user.id, at
    user.last_assigned_at = at
    db.add(
        OwnerHistory(
            donor_id=donor.id,
            from_user_id=None,
            to_user_id=user.id,
            changed_by=actor.user_id,
            method="round_robin",
            changed_at=at,
        )
    )
    audit.write(
        db,
        actor,
        "donor.assign",
        entity="donor",
        entity_id=donor.id,
        data={"to_user_id": user.id, "method": "round_robin"},
        at=at,
    )
    db.flush()
