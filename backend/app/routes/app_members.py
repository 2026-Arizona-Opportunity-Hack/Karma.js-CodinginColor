"""Members, invites and governance. Lane A (Phase 3)."""

from fastapi import APIRouter

from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router, todo
from app.schemas.auth import MeOut
from app.schemas.members import (
    GovernanceDetail,
    InviteAcceptIn,
    InviteIn,
    InviteOut,
    MemberListOut,
    MemberOut,
    MoveDonorsIn,
    MoveDonorsOut,
    ScopeIn,
)
from app.services.ownership import reassign

router = session_router("members")
public_router = APIRouter(prefix="/api/app", tags=["app:members"])


@public_router.post("/auth/invite/{token}/accept", status_code=201)
def accept_invite(token: str, body: InviteAcceptIn) -> MeOut:
    """Open to anyone holding a valid one-time token (AUTH-4)."""
    todo("lane A, phase 3")


@router.get("/members")
def list_members() -> MemberListOut:
    todo("lane A, phase 3")


@router.post("/members/invite", status_code=201)
def invite_member(body: InviteIn) -> InviteOut:
    todo("lane A, phase 3")


@router.post("/members/{member_id}/deactivate")
def deactivate_member(member_id: int) -> MemberOut:
    """Donors stay assigned and appear on Needs reassignment (OWN-5)."""
    todo("lane A, phase 3")


@router.post("/members/{member_id}/move-donors")
def move_donors(
    member_id: int, body: MoveDonorsIn, cur: CurrentDep, db: DB, clock: ClockDep
) -> MoveDonorsOut:
    """Bulk move all donors from one member to another. Super admin only (OWN-3)."""
    return reassign.move_donors(db, clock, cur.actor, member_id, body.to_user_id)


@router.get("/governance")
def get_governance() -> GovernanceDetail:
    todo("lane A, phase 3")


@router.put("/governance/scope")
def set_scope(body: ScopeIn) -> GovernanceDetail:
    todo("lane A, phase 3")


@router.post("/governance/flatten")
def flatten() -> GovernanceDetail:
    """Active super admin becomes dormant; scope returns to `anyone` (GOV-5)."""
    todo("lane A, phase 3")
