"""In-app super admin: nominate, confirm, cancel and remove (GOV-2, GOV-3, D-144)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import CLI
from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from app.services.apikeys import service as keys
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    ana, ben, cy = (seed.add_user(db, n) for n in ("Ana", "Ben", "Cy"))
    donor = seed.add_donor(db, "Ben Donor", owner=ben)
    db.commit()
    return dict(ana=ana, ben=ben, cy=cy, donor=donor)


def login(name: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{name}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    return c


def send(c: TestClient, method: str, path: str, body: dict | None = None):
    return c.request(
        method, f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies.get("cic_csrf")}
    )


def set_governance(db: Session, user: int | None, state: str) -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = :s WHERE id = 1"),
        {"u": user, "s": state},
    )
    db.commit()


def nominate(w, nominee: str, by: str = "ana") -> int:
    r = send(login(by), "POST", "/governance/nominations", {"nominee_user_id": w[nominee]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def audited(db: Session, action: str) -> int:
    return db.execute(
        text("SELECT count(*) FROM audit_log WHERE action = :a"), {"a": action}
    ).scalar_one()


def test_two_different_members_make_the_nominee_super_admin(db: Session, w) -> None:
    nid = nominate(w, "ben")  # Ana nominates Ben
    pending = login("cy").get("/api/app/governance/nominations").json()
    assert pending["id"] == nid and pending["nominee"]["display_name"] == "Ben"
    assert pending["nominated_by"]["display_name"] == "Ana"

    assert send(login("ana"), "POST", f"/governance/nominations/{nid}/confirm").status_code == 403
    r = send(login("cy"), "POST", f"/governance/nominations/{nid}/confirm")
    assert r.status_code == 200
    assert (r.json()["mode"], r.json()["super_admin"]["id"]) == ("super_admin", w["ben"])
    assert login("ben").get("/api/app/auth/me").json()["is_super_admin"] is True
    assert login("ana").get("/api/app/governance/nominations").json() is None
    # create + nomination audit entries for each step
    steps = ("gov.nomination_created", "gov.nomination_confirmed", "gov.super_admin_create")
    assert [audited(db, a) for a in steps] == [1, 1, 1]


def test_the_nominee_may_confirm_when_they_did_not_nominate(db: Session, w) -> None:
    nid = nominate(w, "ben", by="cy")
    assert send(login("ben"), "POST", f"/governance/nominations/{nid}/confirm").status_code == 200


def test_only_one_pending_and_none_while_a_super_admin_is_active(db: Session, w) -> None:
    nominate(w, "ben")
    again = send(login("cy"), "POST", "/governance/nominations", {"nominee_user_id": w["cy"]})
    assert again.status_code == 409  # one pending at a time
    set_governance(db, w["ana"], "active")
    blocked = send(login("cy"), "POST", "/governance/nominations", {"nominee_user_id": w["cy"]})
    assert blocked.status_code == 409
    nid = login("cy").get("/api/app/governance/nominations").json()["id"]
    assert send(login("cy"), "POST", f"/governance/nominations/{nid}/confirm").status_code == 409


def test_expired_and_cancelled_nominations_cannot_be_confirmed(
    db: Session, w, clock: FixedClock
) -> None:
    old = nominate(w, "ben")
    clock.at = T0 + timedelta(hours=72, seconds=1)
    assert login("cy").get("/api/app/governance/nominations").json() is None  # expired on read
    assert send(login("cy"), "POST", f"/governance/nominations/{old}/confirm").status_code == 409

    fresh = nominate(w, "cy")  # the expired one no longer blocks a new nomination
    assert send(login("cy"), "POST", f"/governance/nominations/{fresh}/cancel").status_code == 200
    assert send(login("ben"), "POST", f"/governance/nominations/{fresh}/confirm").status_code == 409
    assert audited(db, "gov.nomination_cancelled") == 1


def test_only_the_nominator_or_nominee_cancels(db: Session, w) -> None:
    nid = nominate(w, "ben")
    assert send(login("cy"), "POST", f"/governance/nominations/{nid}/cancel").status_code == 403
    assert send(login("ana"), "POST", f"/governance/nominations/{nid}/cancel").status_code == 200


def test_a_deactivated_member_cannot_be_nominated(db: Session, w) -> None:
    gone = seed.add_user(db, "Gone", active=False)
    db.commit()
    r = send(login("ana"), "POST", "/governance/nominations", {"nominee_user_id": gone})
    assert r.status_code == 409


def test_only_the_super_admin_removes_the_role_and_the_org_goes_flat(db: Session, w) -> None:
    set_governance(db, w["ben"], "active")
    send(login("ben"), "PUT", "/governance/scope", {"reassign_scope": "own_only"})
    body = {"confirm": "REMOVE"}
    assert send(login("ana"), "DELETE", "/governance/super-admin", body).status_code == 403
    assert (
        send(login("ben"), "DELETE", "/governance/super-admin", {"confirm": "no"}).status_code
        == 400
    )

    r = send(login("ben"), "DELETE", "/governance/super-admin", body)
    assert r.status_code == 200
    assert (r.json()["mode"], r.json()["super_admin_state"], r.json()["reassign_scope"]) == (
        "flat", "none", "anyone",
    )  # fmt: skip
    assert r.json()["super_admin"] is None
    member = next(
        m for m in login("ben").get("/api/app/members").json()["items"] if m["id"] == w["ben"]
    )
    assert member["is_active"] and member["owned_donor_count"] == 1 and not member["is_super_admin"]
    assert audited(db, "gov.super_admin_removed") == 1
    assert send(login("ben"), "DELETE", "/governance/super-admin", body).status_code == 403


def test_a_dormant_super_admin_can_remove_the_role_and_a_new_one_can_follow(db: Session, w) -> None:
    set_governance(db, w["ben"], "dormant")
    assert (
        send(login("ben"), "DELETE", "/governance/super-admin", {"confirm": "REMOVE"}).status_code
        == 200
    )
    nid = nominate(w, "cy", by="ana")
    assert send(login("ben"), "POST", f"/governance/nominations/{nid}/confirm").status_code == 200


def test_full_access_keys_are_denied_on_every_governance_route(db: Session, w) -> None:
    nid = nominate(w, "ben")
    set_governance(db, w["ana"], "dormant")  # flat, so only the key check can say no
    made = keys.create(db, CLI, name="App", scopes=[keys.SCOPE_FULL], created_by=w["cy"])
    db.commit()
    h, c = {"Authorization": f"Bearer {made.key}"}, TestClient(create_app())
    path = "/api/app/governance"
    calls = [
        c.get(f"{path}/nominations", headers=h),
        c.post(f"{path}/nominations", json={"nominee_user_id": w["cy"]}, headers=h),
        c.post(f"{path}/nominations/{nid}/confirm", headers=h),
        c.post(f"{path}/nominations/{nid}/cancel", headers=h),
        c.request("DELETE", f"{path}/super-admin", json={"confirm": "REMOVE"}, headers=h),
    ]
    assert [r.status_code for r in calls] == [403] * 5
