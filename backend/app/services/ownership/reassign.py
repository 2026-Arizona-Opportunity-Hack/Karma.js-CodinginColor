"""Manual and bulk reassignment and owner history (OWN-3, OWN-4)."""

from typing import Any

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.repos import ownership as repo
from app.schemas.common import MemberRef
from app.schemas.donors import DonorDetail, OwnerHistoryEntry, OwnerHistoryOut, ReassignIn
from app.schemas.members import MoveDonorsOut
from app.services.donors import service as donors


def reassign(
    db: Session, clock: Clock, actor: Actor, donor_id: int, body: ReassignIn
) -> DonorDetail:
    repo.reassign(db, actor, donor_id, body.to_user_id, reason=body.reason, at=clock.now())
    return donors.get_donor(db, clock, actor, donor_id)


def move_donors(
    db: Session, clock: Clock, actor: Actor, from_user_id: int, to_user_id: int
) -> MoveDonorsOut:
    return MoveDonorsOut(moved=repo.bulk_move(db, actor, from_user_id, to_user_id, at=clock.now()))


def _ref(r: dict[str, Any], prefix: str) -> MemberRef | None:
    if r[f"{prefix}_id"] is None:
        return None
    return MemberRef(
        id=r[f"{prefix}_id"], display_name=r[f"{prefix}_name"], is_active=r[f"{prefix}_active"]
    )


def owner_history(db: Session, actor: Actor, donor_id: int) -> OwnerHistoryOut:
    items = []
    for r in repo.history(db, actor, donor_id):
        to = _ref(r, "to")
        assert to is not None
        items.append(
            OwnerHistoryEntry(
                id=r["id"], from_user=_ref(r, "from"), to_user=to, changed_by=_ref(r, "by"),
                method=r["method"], reason=r["reason"], changed_at=r["changed_at"],
            )
        )  # fmt: skip
    return OwnerHistoryOut(items=items)
