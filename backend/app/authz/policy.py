"""The one place that decides who may do what (DATA_MODEL 3.6, D-103 to D-105).

Repositories call `can()`; routes never decide on their own. Unknown actions are denied.
Hiding a button is not authorization, so every route is also covered by policy tests.
"""

from enum import StrEnum
from typing import Protocol

from app.authz.actor import Actor


class Action(StrEnum):
    # Donor-scoped: need a resource with an owner.
    DONOR_VIEW = "donor.view"  # gift history, timeline, owner, status (D-104)
    DONOR_VIEW_CONTACT = "donor.view_contact"  # email and phone only (DON-3)
    DONOR_ACT = "donor.act"  # log contact, next step, draft, approve, send (DON-4)
    DONOR_EDIT = "donor.edit"
    DONOR_REASSIGN = "donor.reassign"  # OWN-3
    # Org-wide, any member.
    IMPORT_RUN = "import.run"
    REVIEW_DECIDE = "review.decide"
    # Org-wide, open to every member in flat mode, super admin only while one is active (GOV-4).
    SETTINGS_MANAGE = "settings.manage"
    TEMPLATES_MANAGE = "templates.manage"
    PROGRAMS_MANAGE = "programs.manage"
    INVITE_CREATE = "invite.create"
    APIKEY_MANAGE = "apikey.manage"
    DIGEST_SEND = "digest.send"
    # Super admin only.
    GOV_FLATTEN = "gov.flatten"
    GOV_SET_SCOPE = "gov.set_scope"


DONOR_ACTIONS = frozenset(
    {
        Action.DONOR_VIEW,
        Action.DONOR_VIEW_CONTACT,
        Action.DONOR_ACT,
        Action.DONOR_EDIT,
        Action.DONOR_REASSIGN,
    }
)
ANY_MEMBER = frozenset({Action.IMPORT_RUN, Action.REVIEW_DECIDE})
ADMIN_GATED = frozenset(
    {
        Action.SETTINGS_MANAGE,
        Action.TEMPLATES_MANAGE,
        Action.PROGRAMS_MANAGE,
        Action.INVITE_CREATE,
        Action.APIKEY_MANAGE,
        Action.DIGEST_SEND,
    }
)
SUPER_ADMIN_ONLY = frozenset({Action.GOV_FLATTEN, Action.GOV_SET_SCOPE})


class Owned(Protocol):
    """Anything with an owner, such as a donor. `None` means pending review (DED-5)."""

    owner_user_id: int | None


def can(actor: Actor, action: Action | str, resource: Owned | None = None) -> bool:
    try:
        action = Action(action)
    except ValueError:
        return False  # deny by default

    # The setup CLI is the trusted operator (D-103); the public API key never reaches the app.
    if actor.kind == "cli":
        return True
    if actor.kind != "user":
        return False

    if action in ANY_MEMBER:
        return True
    if action in ADMIN_GATED:
        return actor.is_active_super_admin or not actor.super_admin_active
    if action in SUPER_ADMIN_ONLY:
        return actor.is_active_super_admin
    if action in DONOR_ACTIONS:
        return _donor(actor, action, resource)
    return False


def _donor(actor: Actor, action: Action, resource: Owned | None) -> bool:
    if resource is None:
        return False  # donor actions always name a donor
    if action is Action.DONOR_VIEW:
        return True
    is_owner = resource.owner_user_id is not None and resource.owner_user_id == actor.id
    if is_owner or actor.is_active_super_admin:
        return True
    if action is Action.DONOR_REASSIGN:
        return actor.reassign_scope == "anyone"
    return False
