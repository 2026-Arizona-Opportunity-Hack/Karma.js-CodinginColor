"""Donors, gifts, timeline, ownership, contacts, next steps and reminders.

Lane A builds these (Phase 2 for donors/gifts/timeline/contacts, Phase 3 for ownership and
reminders); lane B consumes them from the generated TypeScript types.
"""

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
    OwnerHistoryOut,
    PossibleDuplicateOut,
    ReassignIn,
    ReminderListOut,
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
    todo("lane A, phase 2")


@router.post(
    "/donors",
    status_code=201,
    responses={409: {"model": PossibleDuplicateOut, "description": "Possible duplicate (DED-6)"}},
)
def create_donor(body: DonorCreate) -> DonorDetail:
    """Runs identity matching first; send `confirm_new: true` to create anyway."""
    todo("lane A, phase 2")


@router.get("/donors/{donor_id}")
def get_donor(donor_id: int) -> DonorDetail:
    """Contact fields are null unless the actor is the owner or an active super admin."""
    todo("lane A, phase 2")


@router.patch("/donors/{donor_id}")
def update_donor(donor_id: int, body: DonorUpdate) -> DonorDetail:
    todo("lane A, phase 2")


@router.delete("/donors/{donor_id}", status_code=204)
def delete_donor(donor_id: int) -> Response:
    """Soft delete only (DON-11)."""
    todo("lane A, phase 2")


@router.post("/donors/{donor_id}/merge", responses={409: {"model": ErrorOut}})
def merge_donor(donor_id: int, body: MergeIn) -> DonorDetail:
    todo("lane A, phase 2")


@router.get("/donors/{donor_id}/timeline")
def get_timeline(donor_id: int) -> TimelineOut:
    todo("lane A, phase 2")


@router.post("/donors/{donor_id}/gifts", status_code=201)
def add_gift(donor_id: int, body: GiftCreate) -> GiftOut:
    todo("lane A, phase 2")


@router.get("/gifts/unattributed")
def list_unattributed_gifts() -> GiftListOut:
    """Anonymous and pending-review gifts (DED-8)."""
    todo("lane A, phase 2")


@router.post("/donors/{donor_id}/reassign")
def reassign_donor(donor_id: int, body: ReassignIn) -> DonorDetail:
    todo("lane A, phase 3")


@router.get("/donors/{donor_id}/owner-history")
def get_owner_history(donor_id: int) -> OwnerHistoryOut:
    todo("lane A, phase 3")


@router.post("/donors/{donor_id}/interactions", status_code=201)
def log_interaction(donor_id: int, body: InteractionCreate) -> InteractionOut:
    todo("lane A, phase 2")


@router.put("/donors/{donor_id}/next-step")
def set_next_step(donor_id: int, body: NextStepIn) -> NextStepOut:
    """One open next step per donor; replaces the current one (DON-10)."""
    todo("lane A, phase 2")


@router.post("/next-steps/{step_id}/done")
def complete_next_step(step_id: int) -> NextStepOut:
    todo("lane A, phase 2")


@router.get("/reminders")
def list_reminders(scope: Annotated[Literal["mine"], Query()] = "mine") -> ReminderListOut:
    """The To-do list: my reminders plus Needs reassignment (REM-5)."""
    todo("lane A, phase 3")


@router.get("/reminders/needs-reassignment")
def list_needs_reassignment() -> ReminderListOut:
    todo("lane A, phase 3")
