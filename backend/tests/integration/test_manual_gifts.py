"""Add a gift by hand, for example a check (DON-8)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from app.repos import reports
from tests import seed

NOW = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)  # Sunday 09:00 in Phoenix, so "today" is Nov 15


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(NOW)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    donor = seed.add_donor(db, "Ann Owner", owner=diana, email="ann@example.org")
    db.commit()
    return dict(diana=diana, sam=sam, donor=donor)


def login(email: str = "diana@example.org") -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post("/api/app/auth/login", json={"email": email, "password": seed.PASSWORD})
    assert r.status_code == 200
    return c


def add(c: TestClient, donor: int, **body):
    body = {"gift_date": "2026-11-10", "gross_cents": 2500, **body}
    headers = {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}
    return c.post(f"/api/app/donors/{donor}/gifts", json=body, headers=headers)


def test_owner_adds_a_gift_that_counts_in_donor_and_org_totals(db: Session, w) -> None:
    c = login()
    r = add(c, w["donor"], gross_cents=12_345)
    assert r.status_code == 201, r.text
    g = r.json()
    assert (g["donor_id"], g["attribution"], g["source"], g["program"]) == (
        w["donor"], "linked", "manual", "General",
    )  # fmt: skip
    assert (g["gross_cents"], g["fee_cents"], g["net_cents"]) == (12_345, 0, 12_345)
    assert g["assumed_thanked"] is False  # a recent gift still owes a thank-you
    d = c.get(f"/api/app/donors/{w['donor']}").json()
    assert d["total_lifetime_cents"] == 12_345 and d["recent_gifts"][0]["id"] == g["id"]
    timeline = c.get(f"/api/app/donors/{w['donor']}/timeline").json()["items"]
    assert any(i["kind"] == "gift" and i["entity_id"] == g["id"] for i in timeline)
    totals = reports.totals(
        db, Actor(kind="user", id=w["diana"]), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    assert (totals["gross_cents"], totals["gift_count"]) == (12_345, 1)


def test_identical_checks_stay_two_gifts_because_row_keys_are_random(db: Session, w) -> None:
    c = login()
    assert add(c, w["donor"]).status_code == add(c, w["donor"]).status_code == 201
    keys = db.execute(text("SELECT row_key FROM gifts")).scalars().all()
    assert len(keys) == 2 and keys[0] != keys[1] and all(len(k) == 64 for k in keys)


def test_program_can_be_chosen_and_an_old_gift_is_assumed_thanked(db: Session, w) -> None:
    c = login()
    camp = db.execute(text("SELECT id FROM programs WHERE name = 'Summer Camp'")).scalar_one()
    assert add(c, w["donor"], program_id=camp).json()["program"] == "Summer Camp"
    assert add(c, w["donor"], program_id=99999).status_code == 400
    assert add(c, w["donor"], gift_date="2026-06-01").json()["assumed_thanked"] is True


def test_bad_input_is_400_and_stores_nothing(db: Session, w) -> None:
    c = login()
    for body in ({"gift_date": "2026-11-16"}, {"gross_cents": 0}, {"note": "paid by check #1042"}):
        assert add(c, w["donor"], **body).status_code == 400, body
    assert db.execute(text("SELECT count(*) FROM gifts")).scalar_one() == 0
    # a note is refused because gifts cannot store one yet (see Known gaps in PHASE_LOG)
    assert "not stored yet" in add(c, w["donor"], note="hi").json()["error"]["message"]


def test_other_member_cannot_add_a_gift_but_an_active_super_admin_can(db: Session, w) -> None:
    sam = login("sam@example.org")
    assert add(sam, w["donor"]).status_code == 403
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
             "WHERE id = 1"),
        {"u": w["sam"]},
    )  # fmt: skip
    db.commit()
    assert add(sam, w["donor"]).status_code == 201


def test_unknown_donor_is_404_and_a_session_is_required(w) -> None:
    assert add(login(), 99999).status_code == 404
    anon = TestClient(create_app())
    body = {"gift_date": "2026-11-10", "gross_cents": 100}
    assert anon.post(f"/api/app/donors/{w['donor']}/gifts", json=body).status_code == 401
