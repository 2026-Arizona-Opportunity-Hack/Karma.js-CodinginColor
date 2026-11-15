"""Super admin lifecycle (GOV-2, GOV-3, GOV-5, GOV-6, GOV-7).

The setup CLI can do everything (break-glass). The app reaches three paths, each through
`policy.can`: `flatten` (the active super admin), `grant` (a confirmed nomination, D-144) and
`remove` (the role holder removing their own role).
"""

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.clock import Clock
from app.db.models import User
from app.errors import Conflict, Forbidden, NotFound
from app.repos import audit, sessions, users


def _require_cli(actor: Actor) -> None:
    if actor.kind != "cli":
        raise PermissionError("super admin changes are CLI-only")


def _user(db: Session, email: str) -> User:
    user = users.find_by_email_for_login(db, email)
    if user is None:
        raise NotFound(f"No board member with email {email}. Run `setup` first.")
    return user


def create(db: Session, actor: Actor, clock: Clock, email: str) -> None:
    _require_cli(actor)
    gov = users.get_governance(db)
    if gov.super_admin_state != "none":
        raise Conflict("A super admin already exists. Use `transfer` or `activate`.")
    user = _user(db, email)
    if not user.is_active:
        raise Conflict("That member is deactivated.")
    gov.super_admin_user_id, gov.super_admin_state, gov.updated_at = user.id, "active", clock.now()
    audit.write(db, actor, "gov.super_admin_create", entity="user", entity_id=user.id)


def activate(db: Session, actor: Actor, clock: Clock) -> None:
    """Re-activate a dormant super admin (after Flatten)."""
    _require_cli(actor)
    gov = users.get_governance(db)
    if gov.super_admin_state != "dormant" or gov.super_admin_user_id is None:
        raise Conflict("No dormant super admin to activate.")
    holder = db.get(User, gov.super_admin_user_id)
    if holder is None or not holder.is_active:
        raise Conflict("The super admin account is deactivated. Use `transfer`.")
    gov.super_admin_state, gov.updated_at = "active", clock.now()
    audit.write(db, actor, "gov.super_admin_activate", entity="user", entity_id=holder.id)


def grant(db: Session, actor: Actor, clock: Clock, user: User) -> None:
    """Make `user` the active super admin while the org is flat. Called when a nomination is
    confirmed; the caller has already checked policy."""
    gov = users.get_governance(db)
    if gov.super_admin_state == "active":
        raise Conflict("The organization already has a super admin.")
    if not user.is_active:
        raise Conflict("That member is deactivated.")
    previous, state = gov.super_admin_user_id, gov.super_admin_state
    gov.super_admin_user_id, gov.super_admin_state, gov.updated_at = user.id, "active", clock.now()
    gov.updated_by = actor.id
    if state == "none":
        audit.write(db, actor, "gov.super_admin_create", entity="user", entity_id=user.id)
    elif previous == user.id:
        audit.write(db, actor, "gov.super_admin_activate", entity="user", entity_id=user.id)
    else:
        audit.write(
            db, actor, "gov.super_admin_transfer", entity="user", entity_id=user.id,
            data={"from_user_id": previous},
        )  # fmt: skip


def remove(db: Session, actor: Actor, clock: Clock) -> None:
    """The role holder deletes their own role (GOV-3). The account and donors stay; the org
    is flat and `reassign_scope` is `anyone`. Works for an active or a dormant super admin."""
    if not can(actor, Action.GOV_REMOVE_SUPER_ADMIN):
        raise Forbidden("Only the super admin can remove the super admin role.")
    gov = users.get_governance(db)
    removed, was = gov.super_admin_user_id, gov.super_admin_state
    gov.super_admin_user_id, gov.super_admin_state, gov.reassign_scope = None, "none", "anyone"
    gov.updated_by, gov.updated_at = actor.id, clock.now()
    audit.write(
        db, actor, "gov.super_admin_removed", entity="user", entity_id=removed,
        data={"was": was},
    )  # fmt: skip


def flatten(db: Session, actor: Actor, clock: Clock) -> None:
    """Role becomes dormant and reassign scope returns to `anyone` (GOV-5 break-glass).
    The setup CLI or the active super admin may do this."""
    if actor.kind != "cli" and not can(actor, Action.GOV_FLATTEN):
        raise Forbidden("Only the active super admin can flatten the hierarchy.")
    gov = users.get_governance(db)
    if gov.super_admin_state != "active":
        raise Conflict("Hierarchy is already flat.")
    gov.super_admin_state, gov.reassign_scope, gov.updated_at = "dormant", "anyone", clock.now()
    audit.write(db, actor, "gov.flatten", entity="user", entity_id=gov.super_admin_user_id)


def transfer(db: Session, actor: Actor, clock: Clock, email: str) -> None:
    """Give the role to another active member. The role is active afterwards."""
    _require_cli(actor)
    gov = users.get_governance(db)
    if gov.super_admin_state == "none":
        raise Conflict("No super admin exists. Use `create`.")
    user = _user(db, email)
    if not user.is_active:
        raise Conflict("That member is deactivated.")
    previous = gov.super_admin_user_id
    gov.super_admin_user_id, gov.super_admin_state, gov.updated_at = user.id, "active", clock.now()
    audit.write(
        db, actor, "gov.super_admin_transfer", entity="user", entity_id=user.id,
        data={"from_user_id": previous},
    )  # fmt: skip


def deactivate(db: Session, actor: Actor, clock: Clock) -> None:
    """Block the super admin account from logging in. The account is never deleted (GOV-3);
    the role goes dormant so nobody is stuck behind super-admin-only settings."""
    _require_cli(actor)
    gov = users.get_governance(db)
    if gov.super_admin_user_id is None:
        raise Conflict("No super admin exists.")
    holder = db.get(User, gov.super_admin_user_id)
    if holder is None:
        raise Conflict("Super admin account missing.")
    now = clock.now()
    users.set_active(db, actor, holder, False, now)
    sessions.revoke_all_for_user(db, holder.id, now)
    gov.super_admin_state, gov.reassign_scope, gov.updated_at = "dormant", "anyone", now
    audit.write(db, actor, "gov.super_admin_deactivate", entity="user", entity_id=holder.id)
