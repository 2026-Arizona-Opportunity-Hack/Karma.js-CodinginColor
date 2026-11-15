"""Governance read, reassignment scope and flatten from the app (GOV-4, GOV-5, GOV-7)."""

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.clock import Clock
from app.db.models import User
from app.errors import Forbidden
from app.repos import audit, users
from app.schemas.common import MemberRef
from app.schemas.members import GovernanceDetail, ScopeIn
from app.services.governance import superadmin


def get(db: Session, actor: Actor) -> GovernanceDetail:
    if not can(actor, Action.DONOR_VIEW, _Anyone()):
        raise Forbidden("Sign in to see governance.")
    gov = users.get_governance(db)
    holder = db.get(User, gov.super_admin_user_id) if gov.super_admin_user_id else None
    return GovernanceDetail(
        mode="super_admin" if gov.super_admin_state == "active" else "flat",
        super_admin_state=gov.super_admin_state,
        reassign_scope=gov.reassign_scope,
        super_admin=MemberRef(
            id=holder.id, display_name=holder.display_name, is_active=holder.is_active
        )
        if holder
        else None,
        updated_at=gov.updated_at,
    )


def set_scope(db: Session, clock: Clock, actor: Actor, body: ScopeIn) -> GovernanceDetail:
    """Only the active super admin; in flat mode the scope stays `anyone`."""
    if not can(actor, Action.GOV_SET_SCOPE):
        raise Forbidden("Only the super admin can change who may reassign donors.")
    gov = users.get_governance(db)
    before = gov.reassign_scope
    gov.reassign_scope, gov.updated_by, gov.updated_at = body.reassign_scope, actor.id, clock.now()
    audit.write(
        db, actor, "gov.set_scope", entity="governance", entity_id=1,
        data={"from": before, "to": body.reassign_scope}, at=gov.updated_at,
    )  # fmt: skip
    db.flush()
    return get(db, actor)


def flatten(db: Session, clock: Clock, actor: Actor) -> GovernanceDetail:
    superadmin.flatten(db, actor, clock)
    db.flush()
    return get(db, actor)


class _Anyone:
    owner_user_id: int | None = None
