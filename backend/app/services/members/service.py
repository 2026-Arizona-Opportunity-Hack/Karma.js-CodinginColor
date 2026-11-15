"""Invites, member list and deactivation (AUTH-4, AUTH-7, OWN-5)."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.authz.actor import SYSTEM, Actor
from app.clock import Clock
from app.db.models import User
from app.repos import audit, members, users
from app.schemas.auth import GovernanceOut, MeOut
from app.schemas.members import (
    InviteAcceptIn,
    InviteIn,
    InviteOut,
    MemberListOut,
    MemberOut,
)
from app.security import hash_password, new_token, sha256_hex

INVITE_HOURS = 72


def _member(user: User, owned: int, is_super_admin: bool) -> MemberOut:
    return MemberOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_super_admin=is_super_admin,
        owned_donor_count=owned,
        created_at=user.created_at,
        deactivated_at=user.deactivated_at,
    )


def list_members(db: Session, actor: Actor) -> MemberListOut:
    rows = members.list_members(db, actor)
    return MemberListOut(items=[_member(r["user"], r["owned"], r["is_super_admin"]) for r in rows])


def invite(db: Session, clock: Clock, actor: Actor, body: InviteIn, *, base_url: str) -> InviteOut:
    """The link is returned once; only its hash is stored. Nothing is emailed."""
    token = new_token()
    at = clock.now()
    row = members.create_invite(
        db, actor, email=body.email.strip().lower(), token_hash=sha256_hex(token), at=at,
        expires_at=at + timedelta(hours=INVITE_HOURS),
    )  # fmt: skip
    return InviteOut(
        id=row.id,
        email=row.email,
        invite_url=base_url.rstrip("/") + "/invite/" + token,
        expires_at=row.expires_at,
    )


def accept(db: Session, clock: Clock, token: str, body: InviteAcceptIn) -> MeOut:
    at = clock.now()
    inv = members.consume_invite(db, sha256_hex(token), at)
    user = users.create(
        db, SYSTEM, email=inv.email, display_name=body.display_name,
        password_hash=hash_password(body.password),
    )  # fmt: skip
    audit.write(
        db, SYSTEM, "member.join", entity="user", entity_id=user.id,
        data={"invite_id": inv.id}, at=at,
    )  # fmt: skip
    gov = users.get_governance(db)
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_super_admin=False,
        governance=GovernanceOut(
            mode="super_admin" if gov.super_admin_state == "active" else "flat",
            reassign_scope=gov.reassign_scope,
        ),
    )


def deactivate(db: Session, clock: Clock, actor: Actor, member_id: int) -> MemberOut:
    user = members.deactivate(db, actor, member_id, at=clock.now())
    owned = next(r["owned"] for r in members.list_members(db, actor) if r["user"].id == user.id)
    return _member(user, owned, False)
