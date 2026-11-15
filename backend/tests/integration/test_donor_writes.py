"""Manual donor entry: create with duplicate warning, edit, soft delete (DON-7, DED-6, DON-11)."""

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
    tom = seed.add_user(db, "Tom", active=False)
    db.commit()
    return dict(diana=diana, sam=sam, alex=alex, tom=tom)


def login(email: str = "sam@example.org") -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    assert (
        c.post("/api/app/auth/login", json={"email": email, "password": seed.PASSWORD}).status_code
        == 200
    )
    return c


def h(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}


def create(c: TestClient, **body):
    return c.post("/api/app/donors", json={"kind": "person", **body}, headers=h(c))


def patch(c: TestClient, donor: int, body: dict):
    return c.patch(f"/api/app/donors/{donor}", json=body, headers=h(c))


# --- create ---------------------------------------------------------------------------------
def test_create_gives_an_owner_normalizes_contact_and_remembers_identities(db: Session, w) -> None:
    r = create(
        login(), display_name="Ada Lovelace", email="  Ada@Example.ORG ", phone="(555) 123-0000",
        organization="Analytical Co",
    )  # fmt: skip
    assert r.status_code == 201, r.text
    d = r.json()
    assert (
        db.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'donor.create'")
        ).scalar_one()
        == 1
    )
    assert d["owner"]["id"] in (w["diana"], w["sam"], w["alex"]) and d["total_lifetime_cents"] == 0
    row = db.execute(
        text("SELECT email, phone, created_via FROM donors WHERE id = :i"), {"i": d["id"]}
    ).one()
    assert tuple(row) == ("ada@example.org", "+15551230000", "manual")
    kinds = db.execute(
        text("SELECT kind FROM donor_identities WHERE donor_id = :i ORDER BY kind"), {"i": d["id"]}
    ).scalars().all()  # fmt: skip
    assert kinds == ["email", "name_org", "phone"]  # so later imports match this donor


def test_new_donors_go_round_robin_to_active_members_only(db: Session, w) -> None:
    for name, owner in (("Old 1", "diana"), ("Old 2", "diana"), ("Old 3", "alex")):
        seed.add_donor(db, name, owner=w[owner])
    db.commit()
    c = login()
    owners = [create(c, display_name=f"Person {i}").json()["owner"]["id"] for i in range(4)]
    assert owners[0] == w["sam"] and w["tom"] not in owners  # Sam had none; Tom is inactive
    history = db.execute(text("SELECT method FROM owner_history")).scalars().all()
    assert history == ["round_robin"] * 4


# --- duplicate warning (DED-6) -------------------------------------------------------------
@pytest.fixture
def grace(db: Session, w) -> int:
    donor = seed.add_donor(
        db, "Grace Hopper", owner=w["diana"], email="grace@navy.example", phone="+15553334444"
    )
    db.execute(text("UPDATE donors SET organization = 'Navy Labs' WHERE id = :i"), {"i": donor})
    db.execute(
        text("INSERT INTO donor_identities (donor_id, kind, value_norm, source) "
             "VALUES (:d, 'name_org', 'grace hopper|navy labs', 'import')"),
        {"d": donor},
    )  # fmt: skip
    db.commit()
    return donor


def test_a_duplicate_email_gives_409_with_candidates_and_confirm_new_creates(
    db: Session, w, grace
) -> None:
    c = login()
    r = create(c, display_name="Grace H", email="GRACE@navy.example")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "possible_duplicate"
    assert r.json()["candidates"] == [
        {
            "donor_id": grace,
            "display_name": "Grace Hopper",
            "owner": {"id": w["diana"], "display_name": "Diana", "is_active": True},
            "match_reason": "email",
        }
    ]
    assert db.execute(text("SELECT count(*) FROM donors")).scalar_one() == 1  # nothing created
    assert (
        create(c, display_name="Grace H", email="grace@navy.example", confirm_new=True).status_code
        == 201
    )


def test_phone_and_name_with_employer_warn_but_a_name_alone_does_not(w, grace) -> None:
    c = login()
    by_phone = create(c, display_name="Someone", phone="(555) 333-4444")
    assert (
        by_phone.status_code == 409 and by_phone.json()["candidates"][0]["match_reason"] == "phone"
    )
    by_employer = create(c, display_name="Grace Hopper", organization="Navy Labs")
    assert by_employer.json()["candidates"][0]["match_reason"] == "name_employer"
    assert create(c, display_name="Grace Hopper").status_code == 201  # a name alone is not a match


def test_bad_input_is_400_and_a_session_is_required(db: Session, w) -> None:
    c = login()
    assert create(c, display_name="A", email="not-an-email").status_code == 400
    assert create(c, display_name="").status_code == 400
    assert db.execute(text("SELECT count(*) FROM donors")).scalar_one() == 0
    anon = TestClient(create_app())
    assert (
        anon.post("/api/app/donors", json={"kind": "person", "display_name": "A"}).status_code
        == 401
    )


# --- edit and delete -----------------------------------------------------------------------
@pytest.fixture
def mine(db: Session, w) -> int:
    donor = seed.add_donor(db, "Ann Owner", owner=w["diana"], email="ann@example.org", notes="n")
    db.commit()
    return donor


def test_owner_edits_and_clears_fields_and_the_new_email_is_remembered(
    db: Session, w, mine
) -> None:
    c = login("diana@example.org")
    r = patch(c, mine, {"display_name": "Ann B. Owner", "phone": "555.777.8888", "notes": None,
                        "email": "ann.new@example.org"})  # fmt: skip
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["display_name"], d["phone"], d["notes"], d["email"]) == (
        "Ann B. Owner", "+15557778888", None, "ann.new@example.org",
    )  # fmt: skip
    dup = create(login(), display_name="Another", email="ann.new@example.org")
    assert dup.status_code == 409 and dup.json()["candidates"][0]["donor_id"] == mine
    audit = db.execute(
        text("SELECT data FROM audit_log WHERE action = 'donor.update'")
    ).scalar_one()
    assert audit == {"fields": ["display_name", "email", "notes", "phone"]}  # names, not values


def test_edit_and_delete_are_for_the_owner_or_an_active_super_admin(db: Session, w, mine) -> None:
    sam = login()
    assert patch(sam, mine, {"notes": "x"}).status_code == 403
    assert sam.delete(f"/api/app/donors/{mine}", headers=h(sam)).status_code == 403
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
             "WHERE id = 1"),
        {"u": w["sam"]},
    )  # fmt: skip
    db.commit()
    assert patch(sam, mine, {"notes": "by super admin"}).status_code == 200
    assert patch(login("diana@example.org"), mine, {}).status_code == 400  # nothing to change


def test_soft_delete_hides_the_donor_but_keeps_gifts_in_org_revenue(db: Session, w, mine) -> None:
    seed.add_gift(db, mine, date(2026, 11, 1), 5000)
    db.commit()
    c = login("diana@example.org")
    assert c.delete(f"/api/app/donors/{mine}", headers=h(c)).status_code == 204
    assert c.get("/api/app/donors", params={"scope": "all"}).json()["total"] == 0
    assert c.get(f"/api/app/donors/{mine}").status_code == 404
    assert db.execute(text("SELECT deleted_at FROM donors WHERE id = :i"), {"i": mine}).one()[0]
    totals = reports.totals(
        db, Actor(kind="user", id=w["diana"]), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    assert totals["gross_cents"] == 5000
