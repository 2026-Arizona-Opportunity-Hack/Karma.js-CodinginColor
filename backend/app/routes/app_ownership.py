"""Ownership changes and derived reminders. Lane A builds these in Phase 3 (OWN, REM)."""

from typing import Annotated, Literal

from fastapi import Query

from app.clock import today
from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router, todo
from app.schemas.donors import (
    DonorDetail,
    OwnerHistoryOut,
    ReassignIn,
    ReminderListOut,
)
from app.services import reminders

router = session_router("ownership")


@router.post("/donors/{donor_id}/reassign")
def reassign_donor(donor_id: int, body: ReassignIn) -> DonorDetail:
    todo("lane A, phase 3")


@router.get("/donors/{donor_id}/owner-history")
def get_owner_history(donor_id: int) -> OwnerHistoryOut:
    todo("lane A, phase 3")


@router.get("/reminders")
def list_reminders(
    cur: CurrentDep,
    db: DB,
    clock: ClockDep,
    scope: Annotated[Literal["mine"], Query()] = "mine",
) -> ReminderListOut:
    """The To-do list: my reminders, most urgent first, then Needs reassignment (REM-5)."""
    assert cur.actor.user_id is not None  # session routes always have a user
    return ReminderListOut(items=reminders.todo_for(db, cur.actor, today(clock), cur.actor.user_id))


@router.get("/reminders/needs-reassignment")
def list_needs_reassignment(cur: CurrentDep, db: DB, clock: ClockDep) -> ReminderListOut:
    return ReminderListOut(items=reminders.needs_reassignment_list(db, cur.actor, today(clock)))
