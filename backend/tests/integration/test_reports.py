"""Report queries shared by /api/v1 and the app's Reports page: summary and retention (RPT-1,
RPT-2, DATA_MODEL 3.5). The fixture test cross-checks the retention SQL against the manifest."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from app.services.reports.retention import classify, windows
from tests import seed
from tests.integration.test_fixtures import run_imports

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)  # Sun 09:00 in Phoenix
TODAY = date(2026, 11, 15)
PW = "correct horse battery"
MANIFEST = json.loads(
    (Path(__file__).resolve().parents[3] / "fixtures" / "manifest.json").read_text()
)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


def member(db: Session) -> TestClient:
    if not db.execute(text("SELECT 1 FROM users WHERE email = 'diana@example.org'")).first():
        seed.add_user(db, "Diana")
        db.commit()
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    assert (
        c.post(
            "/api/app/auth/login", json={"email": "diana@example.org", "password": PW}
        ).status_code
        == 200
    )
    return c


def key_client(db: Session) -> TestClient:
    member(db)  # makes sure a user exists to own the key
    owner = db.execute(text("SELECT id FROM users LIMIT 1")).scalar_one()
    key = seed.add_api_key(db, owner)
    db.commit()
    return TestClient(create_app(), headers={"Authorization": f"Bearer {key}"})


# --- pure classification ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "cur,prev,ever,expected",
    [
        (100, 0, False, "new"),
        (100, 0, True, "reactivated"),
        (200, 100, False, "increased"),
        (100, 100, True, "same"),
        (50, 100, False, "decreased"),
        (0, 100, False, "lapsed"),
        (0, 0, True, None),
        (0, 0, False, None),
    ],
)
def test_classify(cur, prev, ever, expected) -> None:
    assert classify(cur, prev, ever) == expected


def test_rolling_windows_follow_the_definition() -> None:
    cur, prev, before = windows(TODAY, "rolling")
    assert cur == (TODAY - timedelta(days=364), TODAY)  # (T-365, T]
    assert prev == (TODAY - timedelta(days=729), TODAY - timedelta(days=365))  # (T-730, T-365]
    assert before == TODAY - timedelta(days=729)  # gave on or before T-730


def test_calendar_windows() -> None:
    cur, prev, before = windows(date(2026, 6, 30), "calendar")
    assert cur == (date(2026, 1, 1), date(2026, 12, 31))
    assert prev == (date(2025, 1, 1), date(2025, 12, 31)) and before == date(2025, 1, 1)


# --- retention against the database ----------------------------------------------------------
def retention_of(db: Session, **params) -> dict:
    c = member(db)
    r = c.get("/api/app/reports/retention", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def by_name(report: dict) -> dict[str, str]:
    return {d["display_name"]: cls for cls, ds in report["donors"].items() for d in ds}


def test_each_class_and_the_window_edges(db: Session, clock) -> None:
    T = TODAY
    cases = {  # name: gifts
        "New": [(T, 100)],
        "New edge": [(T - timedelta(days=364), 100)],  # first day inside the current window
        "Reactivated": [(T - timedelta(days=800), 50), (T - timedelta(days=10), 100)],
        "Increased": [(T - timedelta(days=500), 100), (T - timedelta(days=10), 300)],
        "Same": [(T - timedelta(days=500), 100), (T - timedelta(days=10), 100)],
        "Decreased": [(T - timedelta(days=500), 300), (T - timedelta(days=10), 100)],
        "Lapsed": [(T - timedelta(days=500), 100)],
        "Lapsed edge": [(T - timedelta(days=365), 100)],  # last day of the previous window
        "Prev edge": [(T - timedelta(days=729), 100)],  # first day of the previous window
        "Too old": [(T - timedelta(days=730), 100)],  # on or before T-730: neither window
        "Future": [(T + timedelta(days=1), 100)],  # after as_of: ignored
    }
    for name, gifts in cases.items():
        d = seed.add_donor(db, name)
        for when, cents in gifts:
            seed.add_gift(db, d, when, cents)
    # things that must never count
    ghost = seed.add_donor(db, "Deleted donor")
    seed.add_gift(db, ghost, T, 100)
    db.execute(text("UPDATE donors SET deleted_at = now() WHERE id = :i"), {"i": ghost})
    removed = seed.add_donor(db, "Removed gift")
    seed.add_gift(db, removed, T, 100, deleted=True)
    seed.add_gift(db, None, T, 100)  # anonymous
    seed.add_gift(db, None, T, 100, attribution="pending_review")
    db.commit()

    report = retention_of(db)
    assert by_name(report) == {
        "New": "new", "New edge": "new", "Reactivated": "reactivated",
        "Increased": "increased", "Same": "same", "Decreased": "decreased",
        "Lapsed": "lapsed", "Lapsed edge": "lapsed", "Prev edge": "lapsed",
    }  # fmt: skip
    assert report["as_of"] == "2026-11-15" and report["basis"] == "rolling"
    assert report["classes"]["new"] == {"donors": 2, "cents_cur": 200, "cents_prev": 0}
    assert report["classes"]["lapsed"] == {"donors": 3, "cents_cur": 0, "cents_prev": 300}
    assert report["classes"]["increased"] == {"donors": 1, "cents_cur": 300, "cents_prev": 100}
    assert (
        set(report["classes"])
        == set(report["donors"])
        == {"new", "reactivated", "increased", "same", "decreased", "lapsed"}
    )  # every class is always present


def test_retention_matches_the_fixture_manifest(db: Session, clock) -> None:
    """Load the independently resolved fixture donors and gifts, then compare class counts and
    cents with fixtures/manifest.json (acceptance test 11, ahead of lane A's importer)."""
    gifts = run_imports()["gifts"]
    for n, items in enumerate(gifts.values()):
        donor = seed.add_donor(db, f"Fixture donor {n}")
        for when, cents in items:
            seed.add_gift(db, donor, when, cents)
    db.commit()
    report = retention_of(db, as_of=MANIFEST["retention"]["as_of"], basis="rolling")
    assert report["classes"] == MANIFEST["retention"]["classes"]
    assert {k: v["donors"] for k, v in report["classes"].items()} == {
        "new": 33, "reactivated": 10, "increased": 25, "same": 18, "decreased": 31, "lapsed": 40,
    }  # fmt: skip
    assert all(len(report["donors"][k]) == v["donors"] for k, v in report["classes"].items())


# --- summary ---------------------------------------------------------------------------------
@pytest.fixture
def money(db: Session, clock) -> None:
    diana = seed.add_user(db, "Diana")
    sam = seed.add_user(db, "Sam", active=False)
    a = seed.add_donor(db, "Ann", owner=diana)
    b = seed.add_donor(db, "Bob", owner=sam)
    seed.add_gift(db, a, date(2026, 11, 3), 10_000, program="AI Academy", fee=500)
    seed.add_gift(db, a, date(2026, 10, 2), 5_001, program="Summer Camp")
    seed.add_gift(db, b, date(2026, 7, 4), 2_500)
    seed.add_gift(db, b, date(2026, 11, 4), 2_500)
    seed.add_gift(db, None, date(2026, 11, 5), 1_000)  # anonymous
    seed.add_gift(db, None, date(2026, 11, 6), 900, attribution="pending_review")
    seed.add_gift(db, a, date(2024, 1, 1), 7_000)  # Ann's first ever gift is long ago
    db.commit()


def test_v1_summary(db: Session, money) -> None:
    c = key_client(db)
    r = c.get("/api/v1/summary", params={"from": "2026-10-01", "to": "2026-11-15"})
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "USD" and body["from"] == "2026-10-01"
    assert body["gross_cents"] == 18_501  # Ann 10,000 + 5,001, Bob 2,500, anonymous 1,000
    assert body["net_cents"] == 18_001  # Ann's first gift had a 500 fee
    assert body["gift_count"] == 4 and body["donor_count"] == 2  # anonymous is not a donor
    assert body["new_donors"] == 0  # Ann first gave in 2024, Bob in July
    assert body["avg_gift_cents"] == 4_625  # 18,501 / 4 = 4,625.25


def test_v1_retention_is_counts_only(db: Session, money) -> None:
    c = key_client(db)
    r = c.get("/api/v1/retention", params={"as_of": "2026-11-15"})
    assert r.status_code == 200
    body = r.json()
    assert body["retention_date"] == "2026-11-15" and body["basis"] == "rolling"
    assert body["currency"] == "USD" and "T" in body["as_of"]
    assert set(body["classes"]) == {
        "new",
        "reactivated",
        "increased",
        "same",
        "decreased",
        "lapsed",
    }
    assert all(set(v) == {"donors", "cents_cur", "cents_prev"} for v in body["classes"].values())
    assert "Ann" not in r.text and "Bob" not in r.text
    assert c.get("/api/v1/retention", params={"basis": "x"}).status_code == 400
    assert TestClient(create_app()).get("/api/v1/retention").status_code == 401


def test_app_summary(db: Session, money) -> None:
    r = member(db).get("/api/app/reports/summary")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["this_month"] == {"gross_cents": 13_500, "gift_count": 3, "donor_count": 2}
    assert s["this_quarter"]["gross_cents"] == 13_500 + 5_001  # Oct and Nov
    assert s["last_12_months"] == {"gross_cents": 21_001, "gift_count": 5, "donor_count": 2}
    assert [(p["program"], p["gross_cents"]) for p in s["by_program"]] == [
        ("AI Academy", 10_000), ("General", 6_000), ("Summer Camp", 5_001),
    ]  # fmt: skip
    boards = {m["member"]["display_name"]: m for m in s["by_board_member"]}
    assert boards["Diana"]["donors_owned"] == 1 and boards["Diana"]["gross_cents"] == 15_001
    assert boards["Sam"]["member"]["is_active"] is False and boards["Sam"]["gross_cents"] == 5_000
    assert s["open_reminders"] == 0 and s["unattributed_gifts"] == 2
    assert TestClient(create_app()).get("/api/app/reports/summary").status_code == 401
