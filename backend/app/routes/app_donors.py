"""Donors, gifts, timeline, contacts and next steps. Lane C builds these in Phase 2 (D-126).

Lane B consumes them from the generated TypeScript types. Ownership changes and reminders
live in app_ownership.py (lane A, Phase 3)."""

from typing import Annotated, Literal

from fastapi import Query, Response
from fastapi.responses import JSONResponse

from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router, todo
from app.schemas.common import DonorStatus, ErrorOut
from app.schemas.donors import (
    DonorCreate,
    DonorDetail,
    DonorPage,
    DonorUpdate,
    GiftCreate,
    GiftListOut,
    GiftOut,
    InteractionCreate,
    InteractionOut,
    MergeIn,
    NextStepIn,
    NextStepOut,
    PossibleDuplicateOut,
    TimelineOut,
)
from app.services.donors import contacts, writes
from app.services.donors import service as donors_service

router = session_router("donors")


@router.get("/donors")
def list_donors(
    cur: CurrentDep,
    db: DB,
    clock: ClockDep,
    scope: Annotated[Literal["mine", "all"], Query()] = "mine",
    q: Annotated[str | None, Query(max_length=100)] = None,
    owner: Annotated[int | None, Query()] = None,
    status: Annotated[DonorStatus | None, Query()] = None,
    program: Annotated[int | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DonorPage:
    return donors_service.list_donors(
        db, clock, cur.actor, scope=scope, q=q, owner=owner, status=status, program=program,
        page=page, page_size=page_size,
    )  # fmt: skip


@router.post(
    "/donors",
    status_code=201,
    response_model=DonorDetail,
    responses={409: {"model": PossibleDuplicateOut, "description": "Possible duplicate (DED-6)"}},
)
def create_donor(
    body: DonorCreate, cur: CurrentDep, db: DB, clock: ClockDep
) -> DonorDetail | JSONResponse:
    """Runs identity matching first; send `confirm_new: true` to create anyway.

    The new donor is given an owner by round-robin (OWN-2) in the same transaction."""
    result = writes.create_donor(db, clock, cur.actor, body)
    if isinstance(result, PossibleDuplicateOut):
        return JSONResponse(status_code=409, content=result.model_dump(mode="json"))
    return result


@router.get("/donors/{donor_id}")
def get_donor(donor_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> DonorDetail:
    """Contact fields are null unless the actor is the owner or an active super admin."""
    return donors_service.get_donor(db, clock, cur.actor, donor_id)


@router.patch("/donors/{donor_id}")
def update_donor(
    donor_id: int, body: DonorUpdate, cur: CurrentDep, db: DB, clock: ClockDep
) -> DonorDetail:
    """Owner and active super admin only (`donor.edit`). Send null to clear an optional field."""
    return writes.update_donor(db, clock, cur.actor, donor_id, body)


@router.delete("/donors/{donor_id}", status_code=204)
def delete_donor(donor_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> Response:
    """Soft delete only (DON-11): gifts and history stay; the donor leaves every list."""
    writes.delete_donor(db, clock, cur.actor, donor_id)
    return Response(status_code=204)


@router.post("/donors/{donor_id}/merge", responses={409: {"model": ErrorOut}})
def merge_donor(donor_id: int, body: MergeIn) -> DonorDetail:
    """SRS priority S: not scheduled for a phase yet (DED-7)."""
    todo("not scheduled")


@router.get("/donors/{donor_id}/timeline")
def get_timeline(donor_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> TimelineOut:
    return donors_service.get_timeline(db, clock, cur.actor, donor_id)


@router.post("/donors/{donor_id}/gifts", status_code=201)
def add_gift(donor_id: int, body: GiftCreate) -> GiftOut:
    todo("lane C, phase 2")


@router.get("/gifts/unattributed")
def list_unattributed_gifts(cur: CurrentDep, db: DB) -> GiftListOut:
    """Anonymous and pending-review gifts (DED-8)."""
    return donors_service.unattributed(db, cur.actor)


@router.post("/donors/{donor_id}/interactions", status_code=201)
def log_interaction(
    donor_id: int, body: InteractionCreate, cur: CurrentDep, db: DB, clock: ClockDep
) -> InteractionOut:
    return contacts.log_interaction(db, clock, cur.actor, donor_id, body)


@router.put("/donors/{donor_id}/next-step")
def set_next_step(
    donor_id: int, body: NextStepIn, cur: CurrentDep, db: DB, clock: ClockDep
) -> NextStepOut:
    """One open next step per donor; replaces the current one (DON-10)."""
    return contacts.set_next_step(db, clock, cur.actor, donor_id, body)


@router.post("/next-steps/{step_id}/done")
def complete_next_step(step_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> NextStepOut:
    return contacts.complete_next_step(db, clock, cur.actor, step_id)
