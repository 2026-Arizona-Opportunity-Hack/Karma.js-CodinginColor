"""Round-robin SQL, serialized with imports and review decisions (DATA_MODEL 3.3)."""

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.authz import policy
from app.authz.actor import Actor
from app.authz.policy import Action
from app.db.models import Donor, OwnerHistory, User
from app.errors import Conflict, Forbidden, Invalid, NotFound
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


# --- manual and bulk reassignment (OWN-3, OWN-4, D-105) ---------------------------------------


def _active_target(db: Session, to_user_id: int) -> User:
    target = db.get(User, to_user_id)
    if target is None or not target.is_active:
        raise Invalid("The new owner must be an active board member.")
    return target


def _move(
    db: Session,
    actor: Actor,
    donor: Donor,
    target: User,
    *,
    method: str,
    reason: str | None,
    at: datetime,
) -> None:
    db.add(
        OwnerHistory(
            donor_id=donor.id,
            from_user_id=donor.owner_user_id,
            to_user_id=target.id,
            changed_by=actor.user_id,
            method=method,
            reason=reason,
            changed_at=at,
        )
    )
    donor.owner_user_id, donor.owner_assigned_at = target.id, at
    target.last_assigned_at = at  # round-robin tie-break counts every hand-off (D-132)


def reassign(
    db: Session, actor: Actor, donor_id: int, to_user_id: int, *, reason: str | None, at: datetime
) -> Donor:
    """One donor to one active member. Scope rules live in `policy.can` (donor.reassign)."""
    donor = db.execute(
        select(Donor)
        .where(Donor.id == donor_id, Donor.deleted_at.is_(None), Donor.merged_into_id.is_(None))
        .with_for_update()
    ).scalar_one_or_none()
    if donor is None:
        raise NotFound("Donor not found.")
    if not policy.can(actor, Action.DONOR_REASSIGN, donor):
        raise Forbidden("You cannot reassign this donor.")
    target = _active_target(db, to_user_id)
    if donor.owner_user_id == target.id:
        raise Conflict("That member already owns this donor.")
    db.execute(text("SELECT pg_advisory_xact_lock(4201)"))  # same lock as round-robin
    before = donor.owner_user_id
    _move(db, actor, donor, target, method="manual", reason=reason, at=at)
    audit.write(
        db, actor, "donor.reassign", entity="donor", entity_id=donor.id,
        data={"from_user_id": before, "to_user_id": target.id, "method": "manual"}, at=at,
    )  # fmt: skip
    db.flush()
    return donor


def bulk_move(
    db: Session, actor: Actor, from_user_id: int, to_user_id: int, *, at: datetime
) -> int:
    """The super admin moves every live donor of one member to another (OWN-3)."""
    if not policy.can(actor, Action.GOV_SET_SCOPE):  # active super admin (or the setup CLI)
        raise Forbidden("Only the super admin can move all of a member's donors.")
    if from_user_id == to_user_id:
        raise Invalid("Pick a different member to move the donors to.")
    if db.get(User, from_user_id) is None:
        raise NotFound("Member not found.")
    target = _active_target(db, to_user_id)
    db.execute(text("SELECT pg_advisory_xact_lock(4201)"))
    donors = list(
        db.scalars(
            select(Donor)
            .where(
                Donor.owner_user_id == from_user_id,
                Donor.deleted_at.is_(None),
                Donor.merged_into_id.is_(None),
            )
            .order_by(Donor.id)
            .with_for_update()
        )
    )
    for donor in donors:
        _move(db, actor, donor, target, method="bulk", reason=None, at=at)
    audit.write(
        db, actor, "donor.bulk_move", entity="user", entity_id=from_user_id,
        data={"to_user_id": target.id, "moved": len(donors)}, at=at,
    )  # fmt: skip
    db.flush()
    return len(donors)


def history(db: Session, actor: Actor, donor_id: int) -> list[dict[str, Any]]:
    """Owner changes, newest first. Visible to every member (OWN-4)."""
    if not policy.can(actor, Action.DONOR_VIEW, _NoOwner()):
        raise Forbidden("Sign in to see owner history.")
    if db.scalar(select(Donor.id).where(Donor.id == donor_id, Donor.deleted_at.is_(None))) is None:
        raise NotFound("Donor not found.")
    sql = """
        SELECT h.id, h.method, h.reason, h.changed_at,
               f.id AS from_id, f.display_name AS from_name, f.is_active AS from_active,
               t.id AS to_id, t.display_name AS to_name, t.is_active AS to_active,
               b.id AS by_id, b.display_name AS by_name, b.is_active AS by_active
        FROM owner_history h
        LEFT JOIN users f ON f.id = h.from_user_id
        JOIN users t ON t.id = h.to_user_id
        LEFT JOIN users b ON b.id = h.changed_by
        WHERE h.donor_id = :d ORDER BY h.changed_at DESC, h.id DESC
    """
    return [dict(r) for r in db.execute(text(sql), {"d": donor_id}).mappings()]


class _NoOwner:
    owner_user_id: int | None = None
