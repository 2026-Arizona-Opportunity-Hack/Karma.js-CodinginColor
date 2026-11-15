"""Member invites, accept and deactivation (AUTH-4, AUTH-7, OWN-5, D-106).
Acceptance test 5: deactivating a member moves no donors and they appear on Needs reassignment."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed

NOW = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(NOW)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    diana, sam, alex = (seed.add_user(db, n) for n in ("Diana", "Sam", "Alex"))
    donor = seed.add_donor(db, "Sam Donor", owner=sam)
    db.commit()
    return dict(diana=diana, sam=sam, alex=alex, donor=donor)


def login(name: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{name}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    return c


def post(c: TestClient, path: str, body: dict | None = None):
    return c.post(f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies.get("cic_csrf")})


def make_super_admin(db: Session, user: int) -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active', "
             "reassign_scope = 'own_only' WHERE id = 1"),
        {"u": user},
    )  # fmt: skip
    db.commit()


def invite(c: TestClient, email: str = "New.Person@Example.org") -> tuple[int, str]:
    r = post(c, "/members/invite", {"email": email})
    assert r.status_code == 201, r.text
    return r.status_code, r.json()["invite_url"].rsplit("/invite/", 1)[1]


def accept(token: str, **body):
    payload = {"display_name": "Nia New", "password": "a long enough password"} | body
    return TestClient(create_app()).post(f"/api/app/auth/invite/{token}/accept", json=payload)


def test_invite_is_one_time_stored_hashed_and_lets_the_person_log_in(db: Session, w) -> None:
    _, token = invite(login("sam"))
    stored = db.execute(text("SELECT token_hash FROM invites")).scalar_one()
    assert token not in stored and len(stored) == 64
    r = accept(token)
    assert r.status_code == 201 and r.json()["email"] == "new.person@example.org"
    # The new member can sign in with the password they chose.
    login_r = TestClient(create_app()).post(
        "/api/app/auth/login",
        json={"email": "new.person@example.org", "password": "a long enough password"},
    )
    assert login_r.status_code == 200
    assert (
        db.execute(text("SELECT count(*) FROM audit_log WHERE action = 'member.join'")).scalar_one()
        == 1
    )
    again = accept(token)  # used
    assert again.status_code == 400
    assert accept("not-a-real-token").json()["error"] == again.json()["error"]  # generic
    assert (
        db.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'member.invite'")
        ).scalar_one()
        == 1
    )


def test_expired_invite_and_existing_member_email_are_refused(db: Session, w, clock) -> None:
    c = login("sam")
    _, token = invite(c)
    assert post(c, "/members/invite", {"email": "ALEX@example.org"}).status_code == 409
    assert post(c, "/members/invite", {"email": "not-an-email"}).status_code == 400
    clock.at = NOW + timedelta(hours=73)
    assert accept(token).status_code == 400


def test_with_an_active_super_admin_only_the_super_admin_invites(db: Session, w) -> None:
    make_super_admin(db, w["diana"])
    assert post(login("sam"), "/members/invite", {"email": "a@example.org"}).status_code == 403
    assert post(login("diana"), "/members/invite", {"email": "a@example.org"}).status_code == 201


def test_deactivating_a_member_moves_no_donors_and_shows_needs_reassignment(db: Session, w) -> None:
    """Acceptance 5."""
    sam = login("sam")
    alex = login("alex")
    r = post(alex, f"/members/{w['sam']}/deactivate")
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert r.json()["owned_donor_count"] == 1
    assert sam.get("/api/app/auth/me").status_code == 401  # session revoked at once
    bad = TestClient(create_app()).post(
        "/api/app/auth/login", json={"email": "sam@example.org", "password": seed.PASSWORD}
    )
    assert bad.status_code == 401
    owner = db.execute(text("SELECT owner_user_id FROM donors WHERE id = :d"), {"d": w["donor"]})
    assert owner.scalar_one() == w["sam"]
    for who in ("alex", "diana"):
        items = login(who).get("/api/app/reminders/needs-reassignment").json()["items"]
        assert [i["donor_id"] for i in items] == [w["donor"]]
    assert (
        db.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'member.deactivate'")
        ).scalar_one()
        == 1
    )
    listed = {m["id"]: m for m in alex.get("/api/app/members").json()["items"]}
    assert listed[w["sam"]]["is_active"] is False and listed[w["sam"]]["owned_donor_count"] == 1


def test_super_admin_and_self_cannot_be_deactivated_and_scope_gates_it(db: Session, w) -> None:
    make_super_admin(db, w["diana"])
    assert post(login("sam"), f"/members/{w['alex']}/deactivate").status_code == 403
    sa = login("diana")
    assert post(sa, f"/members/{w['diana']}/deactivate").status_code == 403  # the super admin
    assert post(sa, f"/members/{w['alex']}/deactivate").status_code == 200
    assert post(sa, f"/members/{w['alex']}/deactivate").status_code == 409  # already
    assert post(sa, "/members/99999/deactivate").status_code == 404
    assert post(login("sam"), f"/members/{w['sam']}/deactivate").status_code == 403


def test_flat_member_cannot_deactivate_self(db: Session, w) -> None:
    assert post(login("sam"), f"/members/{w['sam']}/deactivate").status_code == 400
    assert TestClient(create_app()).get("/api/app/members").status_code == 401
