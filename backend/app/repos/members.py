"""Members, invites and deactivation (AUTH-4, AUTH-7, OWN-5, D-106).

Deactivating never moves donors: they stay assigned and show on Needs reassignment.
Users are never deleted."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import Donor, Invite, User
from app.errors import Conflict, Forbidden, Invalid, NotFound
from app.repos import audit, sessions, users


class _NoOwner:
    owner_user_id: int | None = None


def _require_member(actor: Actor) -> None:
    if not can(actor, Action.DONOR_VIEW, _NoOwner()):
        raise Forbidden("Sign in to see members.")


def list_members(db: Session, actor: Actor) -> list[dict[str, Any]]:
    _require_member(actor)
    gov = users.get_governance(db)
    owned = dict(
        db.execute(
            select(Donor.owner_user_id, func.count())
            .where(
                Donor.deleted_at.is_(None),
                Donor.merged_into_id.is_(None),
                Donor.owner_user_id.isnot(None),
            )
            .group_by(Donor.owner_user_id)
        ).all()
    )
    stmt = select(User).order_by(User.is_active.desc(), func.lower(User.display_name), User.id)
    return [
        {
            "user": u,
            "owned": int(owned.get(u.id, 0)),
            "is_super_admin": gov.super_admin_user_id == u.id,
        }
        for u in db.scalars(stmt)
    ]


def create_invite(
    db: Session, actor: Actor, *, email: str, token_hash: str, at: datetime, expires_at: datetime
) -> Invite:
    if not can(actor, Action.INVITE_CREATE) or actor.id is None:
        raise Forbidden("You cannot invite members.")
    if users.find_by_email_for_login(db, email) is not None:
        raise Conflict("That email already belongs to a board member.")
    invite = Invite(
        email=email,
        token_hash=token_hash,
        created_by=actor.id,
        created_at=at,
        expires_at=expires_at,
    )
    db.add(invite)
    db.flush()
    audit.write(
        db, actor, "member.invite", entity="invite", entity_id=invite.id,
        data={"email": email}, at=at,
    )  # fmt: skip
    return invite


def consume_invite(db: Session, token_hash: str, at: datetime) -> Invite:
    """One generic error for an unknown, used or expired token (AUTH-4)."""
    invite = db.execute(
        select(Invite).where(Invite.token_hash == token_hash).with_for_update()
    ).scalar_one_or_none()
    if (
        invite is None
        or invite.used_at is not None
        or invite.expires_at <= at
        or users.find_by_email_for_login(db, invite.email) is not None
    ):
        raise Invalid("This invite link is not valid. Ask for a new one.")
    invite.used_at = at
    return invite


def deactivate(db: Session, actor: Actor, member_id: int, *, at: datetime) -> User:
    if not can(actor, Action.INVITE_CREATE):
        raise Forbidden("You cannot deactivate members.")
    user = db.execute(
        select(User).where(User.id == member_id).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        raise NotFound("Member not found.")
    gov = users.get_governance(db)
    if gov.super_admin_user_id == user.id:
        raise Forbidden("The super admin can only be changed with the setup command.")
    if user.id == actor.id:
        raise Invalid("You cannot deactivate yourself.")
    if not user.is_active:
        raise Conflict("That member is already deactivated.")
    user.is_active, user.deactivated_at = False, at
    sessions.revoke_all_for_user(db, user.id, at)
    kept = db.execute(
        text("SELECT count(*) FROM donors WHERE owner_user_id = :u AND deleted_at IS NULL"),
        {"u": user.id},
    ).scalar_one()
    audit.write(
        db, actor, "member.deactivate", entity="user", entity_id=user.id,
        data={"donors_left_assigned": kept}, at=at,
    )  # fmt: skip
    db.flush()
    return user
