"""Members, invites and governance. Lane A (Phase 3)."""

from fastapi import APIRouter, Request

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
from app.services.members import service as members

router = session_router("members")
public_router = APIRouter(prefix="/api/app", tags=["app:members"])


@public_router.post("/auth/invite/{token}/accept", status_code=201)
def accept_invite(token: str, body: InviteAcceptIn, db: DB, clock: ClockDep) -> MeOut:
    """Open to anyone holding a valid one-time token (AUTH-4)."""
    return members.accept(db, clock, token, body)


@router.get("/members")
def list_members(cur: CurrentDep, db: DB) -> MemberListOut:
    return members.list_members(db, cur.actor)


@router.post("/members/invite", status_code=201)
def invite_member(
    body: InviteIn, request: Request, cur: CurrentDep, db: DB, clock: ClockDep
) -> InviteOut:
    """One-time link, valid 72 hours, shown once (AUTH-4)."""
    return members.invite(db, clock, cur.actor, body, base_url=str(request.base_url))


@router.post("/members/{member_id}/deactivate")
def deactivate_member(member_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> MemberOut:
    """Donors stay assigned and appear on Needs reassignment (OWN-5)."""
    return members.deactivate(db, clock, cur.actor, member_id)


@router.post("/members/{member_id}/move-donors")
def move_donors(member_id: int, body: MoveDonorsIn) -> MoveDonorsOut:
    """Bulk move all donors from one member to another. Super admin only (OWN-3)."""
    todo("lane A, phase 3")


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
