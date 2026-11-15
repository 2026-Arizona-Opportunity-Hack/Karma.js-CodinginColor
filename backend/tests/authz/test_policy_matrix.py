"""Table-driven policy tests: every action x role x ownership x governance state.

Expectations are written out by hand from DATA_MODEL 3.6 (and SRS DON/OWN/GOV), not
derived from the policy's own logic, so a wrong rule shows up as a failing row.
"""

from dataclasses import dataclass

import pytest

from app.authz.actor import Actor
from app.authz.policy import Action, can

OWNER_ID, OTHER_ID, SA_ID = 1, 2, 3


@dataclass(frozen=True)
class Donor:
    owner_user_id: int | None


# Governance states: (super admin active?, reassign scope, is the super admin dormant?)
STATES = {
    "flat": dict(super_admin_active=False, reassign_scope="anyone"),
    "sa_active_anyone": dict(super_admin_active=True, reassign_scope="anyone"),
    "sa_active_own_only": dict(super_admin_active=True, reassign_scope="own_only"),
    "sa_dormant": dict(super_admin_active=False, reassign_scope="anyone"),
}


def actor(role: str, state: str) -> Actor:
    """role: owner | other | sa (the super admin user, not the owner of the donor)."""
    gov = STATES[state]
    uid = {"owner": OWNER_ID, "other": OTHER_ID, "sa": SA_ID}[role]
    is_active_sa = role == "sa" and state.startswith("sa_active")
    holds_role = role == "sa" and state.startswith("sa_")  # active or dormant
    return Actor(  # type: ignore[arg-type]
        kind="user", id=uid, is_active_super_admin=is_active_sa,
        holds_super_admin_role=holds_role, **gov,
    )  # fmt: skip


T, F = True, False
ALL_STATES = {s: T for s in STATES}
NO_STATES = {s: F for s in STATES}

# action -> role -> {state: allowed}. Roles act on a donor owned by `owner`.
DONOR_MATRIX: dict[Action, dict[str, dict[str, bool]]] = {
    Action.DONOR_VIEW: {"owner": ALL_STATES, "other": ALL_STATES, "sa": ALL_STATES},
    Action.DONOR_VIEW_CONTACT: {"owner": ALL_STATES, "other": NO_STATES, "sa": {
        "flat": F, "sa_active_anyone": T, "sa_active_own_only": T, "sa_dormant": F}},
    Action.DONOR_ACT: {"owner": ALL_STATES, "other": NO_STATES, "sa": {
        "flat": F, "sa_active_anyone": T, "sa_active_own_only": T, "sa_dormant": F}},
    Action.DONOR_EDIT: {"owner": ALL_STATES, "other": NO_STATES, "sa": {
        "flat": F, "sa_active_anyone": T, "sa_active_own_only": T, "sa_dormant": F}},
    Action.DONOR_REASSIGN: {
        "owner": ALL_STATES,
        "other": {"flat": T, "sa_active_anyone": T, "sa_active_own_only": F, "sa_dormant": T},
        "sa": {"flat": T, "sa_active_anyone": T, "sa_active_own_only": T, "sa_dormant": T},
    },
}  # fmt: skip
# In the "flat" and "sa_dormant" rows the "sa" user is just another board member.


def donor_cases():
    for action, by_role in DONOR_MATRIX.items():
        for role, by_state in by_role.items():
            for state, expected in by_state.items():
                yield pytest.param(action, role, state, expected, id=f"{action}-{role}-{state}")


@pytest.mark.parametrize("action,role,state,expected", list(donor_cases()))
def test_donor_actions(action: Action, role: str, state: str, expected: bool) -> None:
    assert can(actor(role, state), action, Donor(owner_user_id=OWNER_ID)) is expected


# Org-wide actions: action -> {role: {state: allowed}} (no donor involved).
ANY_MEMBER = {role: ALL_STATES for role in ("owner", "other", "sa")}
ADMIN_GATED = {  # flat or dormant: every member; active super admin: only the super admin
    "owner": {"flat": T, "sa_active_anyone": F, "sa_active_own_only": F, "sa_dormant": T},
    "other": {"flat": T, "sa_active_anyone": F, "sa_active_own_only": F, "sa_dormant": T},
    "sa": ALL_STATES,
}
SA_ONLY = {
    "owner": NO_STATES,
    "other": NO_STATES,
    "sa": {"flat": F, "sa_active_anyone": T, "sa_active_own_only": T, "sa_dormant": F},
}
FLAT_ONLY = {
    role: {"flat": T, "sa_active_anyone": F, "sa_active_own_only": F, "sa_dormant": T}
    for role in ("owner", "other", "sa")
}
HOLDER_ONLY = {
    "owner": NO_STATES,
    "other": NO_STATES,
    "sa": {"flat": F, "sa_active_anyone": T, "sa_active_own_only": T, "sa_dormant": T},
}
ORG_MATRIX: dict[Action, dict[str, dict[str, bool]]] = {
    Action.IMPORT_RUN: ANY_MEMBER,
    Action.REVIEW_DECIDE: ANY_MEMBER,
    Action.SETTINGS_MANAGE: ADMIN_GATED,
    Action.TEMPLATES_MANAGE: ADMIN_GATED,
    Action.PROGRAMS_MANAGE: ADMIN_GATED,
    Action.INVITE_CREATE: ADMIN_GATED,
    Action.APIKEY_MANAGE: ADMIN_GATED,
    Action.DIGEST_SEND: ADMIN_GATED,
    Action.GOV_FLATTEN: SA_ONLY,
    Action.GOV_SET_SCOPE: SA_ONLY,
    # Nominating and confirming: any member while flat (a dormant super admin counts as flat).
    Action.GOV_NOMINATE: FLAT_ONLY,
    Action.GOV_CONFIRM_NOMINATION: FLAT_ONLY,
    # Removing the role: only its holder, active or dormant.
    Action.GOV_REMOVE_SUPER_ADMIN: HOLDER_ONLY,
}


def org_cases():
    for action, by_role in ORG_MATRIX.items():
        for role, by_state in by_role.items():
            for state, expected in by_state.items():
                yield pytest.param(action, role, state, expected, id=f"{action}-{role}-{state}")


@pytest.mark.parametrize("action,role,state,expected", list(org_cases()))
def test_org_actions(action: Action, role: str, state: str, expected: bool) -> None:
    assert can(actor(role, state), action) is expected


def test_every_action_is_covered_by_the_matrix() -> None:
    covered = set(DONOR_MATRIX) | set(ORG_MATRIX)
    assert covered == set(Action), f"untested actions: {set(Action) - covered}"


def test_matrix_size_for_the_trust_report() -> None:
    n = len(list(donor_cases())) + len(list(org_cases()))
    assert n == 5 * 3 * 4 + 13 * 3 * 4  # 216 rows


# --- ownership edge cases ---


@pytest.mark.parametrize("action", [Action.DONOR_VIEW_CONTACT, Action.DONOR_ACT, Action.DONOR_EDIT])
def test_unowned_donor_pending_review_is_not_owned_by_anyone(action: Action) -> None:
    pending = Donor(owner_user_id=None)
    assert can(actor("owner", "flat"), action, pending) is False
    assert can(actor("other", "flat"), action, pending) is False
    assert can(actor("sa", "sa_active_anyone"), action, pending) is True


def test_everyone_can_view_an_unowned_donor() -> None:
    assert can(actor("other", "flat"), Action.DONOR_VIEW, Donor(owner_user_id=None)) is True


def test_actor_without_an_id_never_matches_an_unowned_donor() -> None:
    nobody = Actor(kind="user", id=None)
    assert can(nobody, Action.DONOR_ACT, Donor(owner_user_id=None)) is False


def test_donor_actions_need_a_donor() -> None:
    for action in DONOR_MATRIX:
        assert can(actor("owner", "flat"), action) is False


def test_owner_inactive_donor_follows_the_same_rules() -> None:
    """Deactivated owner: nobody is the owner, so only the scope and super admin decide (OWN-5)."""
    donor = Donor(owner_user_id=99)  # the deactivated member
    assert can(actor("other", "flat"), Action.DONOR_REASSIGN, donor) is True
    assert can(actor("other", "sa_active_own_only"), Action.DONOR_REASSIGN, donor) is False
    assert can(actor("sa", "sa_active_own_only"), Action.DONOR_REASSIGN, donor) is True
    assert can(actor("other", "flat"), Action.DONOR_ACT, donor) is False


# --- non-user actors and bad input ---


@pytest.mark.parametrize("action", list(Action))
def test_api_keys_and_system_never_pass_policy(action: Action) -> None:
    donor = Donor(owner_user_id=OWNER_ID)
    for kind in ("api_key", "system"):
        assert can(Actor(kind=kind, id=1), action, donor) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("action", list(Action))
def test_setup_cli_is_the_trusted_operator(action: Action) -> None:
    assert can(Actor(kind="cli", id=None), action, Donor(owner_user_id=OWNER_ID)) is True


@pytest.mark.parametrize("bad", ["", "donor.delete", "donor.view ", "DONOR.VIEW", "root", "*"])
def test_unknown_actions_are_denied(bad: str) -> None:
    assert can(actor("sa", "sa_active_anyone"), bad, Donor(owner_user_id=OWNER_ID)) is False
    assert can(Actor(kind="cli", id=None), bad) is False


def test_actions_may_be_passed_as_plain_strings() -> None:
    assert can(actor("owner", "flat"), "donor.act", Donor(owner_user_id=OWNER_ID)) is True


def test_action_names_are_stable() -> None:
    """These strings appear in audit entries and docs; renaming one must be deliberate."""
    assert {a.value for a in Action} == {
        "donor.view", "donor.view_contact", "donor.act", "donor.edit", "donor.reassign",
        "import.run", "review.decide", "settings.manage", "templates.manage",
        "programs.manage", "invite.create", "apikey.manage", "digest.send",
        "gov.flatten", "gov.set_scope", "gov.nominate", "gov.confirm_nomination",
        "gov.remove_super_admin",
    }  # fmt: skip
