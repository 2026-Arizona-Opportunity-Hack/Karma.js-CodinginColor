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
PW = "correct horse battery"


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
    gone = seed.add_donor(db, "Gone Gary", owner=diana, deleted=True)
    db.commit()
    return dict(diana=diana, sam=sam, donor=donor, gone=gone)


def login(email: str = "diana@example.org") -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    assert c.post("/api/app/auth/login", json={"email": email, "password": PW}).status_code == 200
    return c


def add(c: TestClient, donor: int, **body):
    body = {"gift_date": "2026-11-10", "gross_cents": 2500, **body}
    return c.post(f"/api/app/donors/{donor}/gifts", json=body, headers=h(c))


def h(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}


def test_owner_adds_a_gift_that_counts_everywhere(db: Session, w) -> None:
    c = login()
    r = add(c, w["donor"], gross_cents=12_345)
    assert r.status_code == 201, r.text
    g = r.json()
    assert (g["donor_id"], g["donor_name"], g["attribution"], g["source"]) == (
        w["donor"], "Ann Owner", "linked", "manual",
    )  # fmt: skip
    assert (g["gift_date"], g["gross_cents"], g["fee_cents"], g["net_cents"]) == (
        "2026-11-10", 12_345, 0, 12_345,
    )  # fmt: skip
    assert g["program"] == "General" and g["is_matching_gift"] is False
    assert g["assumed_thanked"] is False  # a recent gift still owes a thank-you
    d = c.get(f"/api/app/donors/{w['donor']}").json()
    assert d["total_lifetime_cents"] == 12_345 and d["last_gift_date"] == "2026-11-10"
    assert d["recent_gifts"][0]["id"] == g["id"]
    timeline = c.get(f"/api/app/donors/{w['donor']}/timeline").json()["items"]
    assert any(i["kind"] == "gift" and i["entity_id"] == g["id"] for i in timeline)
    totals = reports.totals(
        db, Actor(kind="user", id=w["diana"]), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    assert (totals["gross_cents"], totals["gift_count"]) == (12_345, 1)


def test_row_keys_are_random_so_identical_checks_stay_separate(db: Session, w) -> None:
    c = login()
    first, second = add(c, w["donor"]), add(c, w["donor"])
    assert first.status_code == second.status_code == 201
    keys = [r[0] for r in db.execute(text("SELECT row_key FROM gifts ORDER BY id")).all()]
    assert len(keys) == 2 and keys[0] != keys[1]
    assert all(len(k) == 64 and int(k, 16) >= 0 for k in keys)  # sha256 hex
    d = c.get(f"/api/app/donors/{w['donor']}").json()
    assert d["total_lifetime_cents"] == 5000


def test_program_defaults_to_general_and_can_be_chosen(db: Session, w) -> None:
    c = login()
    camp = db.execute(text("SELECT id FROM programs WHERE name = 'Summer Camp'")).scalar_one()
    assert add(c, w["donor"], program_id=camp).json()["program"] == "Summer Camp"
    db.execute(text("UPDATE programs SET is_active = false WHERE name = 'K12 Program'"))
    db.commit()
    inactive = db.execute(text("SELECT id FROM programs WHERE name = 'K12 Program'")).scalar_one()
    for bad in (99999, inactive):
        assert add(c, w["donor"], program_id=bad).status_code == 400


def test_a_gift_older_than_the_cutoff_is_assumed_thanked(db: Session, w) -> None:
    c = login()
    old = add(c, w["donor"], gift_date="2026-06-01").json()
    edge = add(c, w["donor"], gift_date="2026-09-16").json()  # 60 days before Nov 15: not older
    assert old["assumed_thanked"] is True and edge["assumed_thanked"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"gift_date": "2026-11-16"},  # tomorrow
        {"gift_date": "yesterday"},
        {"gross_cents": 0},
        {"gross_cents": -5},
        {"gross_cents": 10_000_000_001},
        {"gross_cents": 12.5},
        {"gross_cents": "lots"},
        {"note": "paid by check #1042"},  # not stored yet: refused rather than dropped
    ],
)
def test_bad_input_is_400_and_stores_nothing(db: Session, w, body) -> None:
    r = add(login(), w["donor"], **body)
    assert r.status_code == 400, r.text
    assert db.execute(text("SELECT count(*) FROM gifts")).scalar_one() == 0


def test_missing_fields_are_400_and_an_empty_note_is_fine(db: Session, w) -> None:
    c = login()
    assert c.post(f"/api/app/donors/{w['donor']}/gifts", json={}, headers=h(c)).status_code == 400
    assert add(c, w["donor"], note="").status_code == 201
    assert add(c, w["donor"], note=None).status_code == 201


def test_note_refusal_message_tells_the_user_what_to_do(db: Session, w) -> None:
    r = add(login(), w["donor"], note="hello")
    assert "Gift notes are not stored yet" in r.json()["error"]["message"]


def test_other_member_cannot_add_a_gift_but_an_active_super_admin_can(db: Session, w) -> None:
    sam = login("sam@example.org")
    assert add(sam, w["donor"]).status_code == 403
    assert db.execute(text("SELECT count(*) FROM gifts")).scalar_one() == 0
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
             "WHERE id = 1"),
        {"u": w["sam"]},
    )  # fmt: skip
    db.commit()
    assert add(sam, w["donor"]).status_code == 201


def test_unknown_or_deleted_donor_is_404_and_access_needs_a_session_and_csrf(w) -> None:
    c = login()
    assert add(c, 99999).status_code == 404
    assert add(c, w["gone"]).status_code == 404
    path = f"/api/app/donors/{w['donor']}/gifts"
    body = {"gift_date": "2026-11-10", "gross_cents": 100}
    assert TestClient(create_app()).post(path, json=body).status_code == 401
    assert c.post(path, json=body).status_code == 403  # no CSRF header


def test_the_audit_entry_has_ids_only(db: Session, w) -> None:
    g = add(login(), w["donor"], gross_cents=777).json()
    rows = db.execute(
        text("SELECT action, entity, entity_id, data FROM audit_log WHERE action = 'gift.create'")
    ).all()
    assert [tuple(r) for r in rows] == [
        ("gift.create", "gift", g["id"], {"donor_id": w["donor"], "source": "manual"})
    ]
    created_by = db.execute(text("SELECT created_by FROM gifts WHERE id = :i"), {"i": g["id"]})
    assert created_by.scalar_one() == w["diana"]
