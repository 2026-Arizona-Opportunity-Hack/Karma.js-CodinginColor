"""Members, invites and governance. Lane A (Phase 3)."""

from fastapi import APIRouter, Request

from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router
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
    NominationIn,
    NominationOut,
    RemoveSuperAdminIn,
    ScopeIn,
)
from app.services.governance import nominations
from app.services.governance import service as governance
from app.services.members import service as members
from app.services.ownership import reassign

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
def move_donors(
    member_id: int, body: MoveDonorsIn, cur: CurrentDep, db: DB, clock: ClockDep
) -> MoveDonorsOut:
    """Bulk move all donors from one member to another. Super admin only (OWN-3)."""
    return reassign.move_donors(db, clock, cur.actor, member_id, body.to_user_id)


@router.get("/governance")
def get_governance(cur: CurrentDep, db: DB) -> GovernanceDetail:
    return governance.get(db, cur.actor)


@router.put("/governance/scope")
def set_scope(body: ScopeIn, cur: CurrentDep, db: DB, clock: ClockDep) -> GovernanceDetail:
    """Active super admin only (GOV-4)."""
    return governance.set_scope(db, clock, cur.actor, body)


@router.post("/governance/flatten")
def flatten(cur: CurrentDep, db: DB, clock: ClockDep) -> GovernanceDetail:
    """Active super admin becomes dormant; scope returns to `anyone` (GOV-5)."""
    return governance.flatten(db, clock, cur.actor)


@router.get("/governance/nominations")
def get_nomination(cur: CurrentDep, db: DB, clock: ClockDep) -> NominationOut | None:
    """The pending super admin nomination, or null. Expired ones are not returned (GOV-2)."""
    return nominations.pending(db, clock, cur.actor)


@router.post("/governance/nominations", status_code=201)
def nominate(body: NominationIn, cur: CurrentDep, db: DB, clock: ClockDep) -> NominationOut:
    """Any active member, while the org is flat. One pending nomination at a time (GOV-2)."""
    return nominations.nominate(db, clock, cur.actor, body.nominee_user_id)


@router.post("/governance/nominations/{nomination_id}/confirm")
def confirm_nomination(
    nomination_id: int, cur: CurrentDep, db: DB, clock: ClockDep
) -> GovernanceDetail:
    """A different member than the nominator makes the nominee super admin (GOV-2)."""
    return nominations.confirm(db, clock, cur.actor, nomination_id)


@router.post("/governance/nominations/{nomination_id}/cancel")
def cancel_nomination(
    nomination_id: int, cur: CurrentDep, db: DB, clock: ClockDep
) -> NominationOut:
    """The nominator or the nominee withdraws a pending nomination."""
    return nominations.cancel(db, clock, cur.actor, nomination_id)


@router.delete("/governance/super-admin")
def remove_super_admin(
    body: RemoveSuperAdminIn, cur: CurrentDep, db: DB, clock: ClockDep
) -> GovernanceDetail:
    """The super admin removes their own role; the org becomes flat (GOV-3). Body: REMOVE."""
    return governance.remove_super_admin(db, clock, cur.actor)
