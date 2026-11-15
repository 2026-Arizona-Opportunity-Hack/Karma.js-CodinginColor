"""Ownership changes and derived reminders. Lane A builds these in Phase 3 (OWN, REM)."""

from typing import Annotated, Literal

from fastapi import Query

from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router, todo
from app.schemas.donors import (
    DonorDetail,
    OwnerHistoryOut,
    ReassignIn,
    ReminderListOut,
)
from app.services.ownership import reassign

router = session_router("ownership")


@router.post("/donors/{donor_id}/reassign")
def reassign_donor(
    donor_id: int, body: ReassignIn, cur: CurrentDep, db: DB, clock: ClockDep
) -> DonorDetail:
    """Hand a donor to an active member, per the reassign scope (OWN-3)."""
    return reassign.reassign(db, clock, cur.actor, donor_id, body)


@router.get("/donors/{donor_id}/owner-history")
def get_owner_history(donor_id: int, cur: CurrentDep, db: DB) -> OwnerHistoryOut:
    return reassign.owner_history(db, cur.actor, donor_id)


@router.get("/reminders")
def list_reminders(scope: Annotated[Literal["mine"], Query()] = "mine") -> ReminderListOut:
    """The To-do list: my reminders plus Needs reassignment (REM-5)."""
    todo("lane A, phase 3")


@router.get("/reminders/needs-reassignment")
def list_needs_reassignment() -> ReminderListOut:
    todo("lane A, phase 3")
