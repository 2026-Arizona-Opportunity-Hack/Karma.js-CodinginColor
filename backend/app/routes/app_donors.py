"""Donors, gifts, timeline, contacts and next steps. Lane C builds these in Phase 2 (D-126).

Lane B consumes them from the generated TypeScript types. Ownership changes and reminders
live in app_ownership.py (lane A, Phase 3)."""

from typing import Annotated, Literal

from fastapi import Query, Response

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

router = session_router("donors")


@router.get("/donors")
def list_donors(
    scope: Annotated[Literal["mine", "all"], Query()] = "mine",
    q: Annotated[str | None, Query(max_length=100)] = None,
    owner: Annotated[int | None, Query()] = None,
    status: Annotated[DonorStatus | None, Query()] = None,
    program: Annotated[int | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DonorPage:
    todo("lane C, phase 2")


@router.post(
    "/donors",
    status_code=201,
    responses={409: {"model": PossibleDuplicateOut, "description": "Possible duplicate (DED-6)"}},
)
def create_donor(body: DonorCreate) -> DonorDetail:
    """Runs identity matching first; send `confirm_new: true` to create anyway."""
    todo("lane C, phase 2")


@router.get("/donors/{donor_id}")
def get_donor(donor_id: int) -> DonorDetail:
    """Contact fields are null unless the actor is the owner or an active super admin."""
    todo("lane C, phase 2")


@router.patch("/donors/{donor_id}")
def update_donor(donor_id: int, body: DonorUpdate) -> DonorDetail:
    todo("lane C, phase 2")


@router.delete("/donors/{donor_id}", status_code=204)
def delete_donor(donor_id: int) -> Response:
    """Soft delete only (DON-11)."""
    todo("lane C, phase 2")


@router.post("/donors/{donor_id}/merge", responses={409: {"model": ErrorOut}})
def merge_donor(donor_id: int, body: MergeIn) -> DonorDetail:
    """SRS priority S: not scheduled for a phase yet (DED-7)."""
    todo("not scheduled")


@router.get("/donors/{donor_id}/timeline")
def get_timeline(donor_id: int) -> TimelineOut:
    todo("lane C, phase 2")


@router.post("/donors/{donor_id}/gifts", status_code=201)
def add_gift(donor_id: int, body: GiftCreate) -> GiftOut:
    todo("lane C, phase 2")


@router.get("/gifts/unattributed")
def list_unattributed_gifts() -> GiftListOut:
    """Anonymous and pending-review gifts (DED-8)."""
    todo("lane C, phase 2")


@router.post("/donors/{donor_id}/interactions", status_code=201)
def log_interaction(donor_id: int, body: InteractionCreate) -> InteractionOut:
    todo("lane C, phase 2")


@router.put("/donors/{donor_id}/next-step")
def set_next_step(donor_id: int, body: NextStepIn) -> NextStepOut:
    """One open next step per donor; replaces the current one (DON-10)."""
    todo("lane C, phase 2")


@router.post("/next-steps/{step_id}/done")
def complete_next_step(step_id: int) -> NextStepOut:
    todo("lane C, phase 2")
