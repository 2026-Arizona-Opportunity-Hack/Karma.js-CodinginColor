"""Funder export (RPT-3, DON-12, D-127, D-129): contents, formula neutralizing, escaping,
contact rules and the audit entry."""

import csv
import io
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed

TODAY = date(2026, 11, 15)


@pytest.fixture(autouse=True)
def clock() -> Iterator[None]:
    set_clock(FixedClock(datetime(2026, 11, 15, 16, 0, tzinfo=UTC)))
    yield
    set_clock(SystemClock())


def login(name: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{name}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    return c


def world(db: Session, donor_name: str = "Acme Foundation") -> dict[str, int]:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    donor = seed.add_donor(
        db, donor_name, owner=diana, email="grants@acme.example", phone="+15551230000",
        notes="Prefers calls", kind="organization",
    )  # fmt: skip
    seed.add_gift(db, donor, date(2026, 3, 1), 50_000)
    seed.add_gift(db, donor, date(2026, 5, 1), 25_000)
    match = seed.add_gift(db, donor, date(2026, 6, 1), 40_000)
    db.execute(text("UPDATE gifts SET is_matching_gift = true WHERE id = :g"), {"g": match})
    seed.add_gift(db, donor, date(2024, 1, 1), 99_000)  # outside the default window
    pid = db.execute(text("SELECT id FROM programs WHERE name = 'General'")).scalar_one()
    db.execute(
        text(
            "INSERT INTO program_outcomes (program_id, period_start, period_end, metric_label, "
            "value, unit) VALUES (:p, '2026-01-01', '2026-06-30', '=HYPERLINK(\"x\")', 120, 'kids')"
        ),
        {"p": pid},
    )
    db.commit()
    return {"diana": diana, "sam": sam, "donor": donor}


def rows(body: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body)))


def test_csv_has_own_giving_outcomes_and_the_match_note_without_the_match(db: Session) -> None:
    w = world(db)
    r = login("sam").get(f"/api/app/reports/funder/{w['donor']}?format=csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    got = rows(r.text)
    gifts = [x for x in got if x[0] == "gifts"]
    assert [(x[1], x[3], x[4]) for x in gifts] == [("General", "2", "750.00")]  # no match, no 2024
    assert any(x[0] == "outcome" and x[6] == "120" and x[7] == "kids" for x in got)
    assert any("matching gifts are not included" in x[8] for x in got if x[0] == "note")
    assert next(x for x in got if x[0] == "excluded_matches")[4] == "400.00"


def test_csv_cells_that_start_like_formulas_are_neutralized(db: Session) -> None:
    w = world(db, donor_name="=cmd|' /C calc'!A0")
    got = rows(login("diana").get(f"/api/app/reports/funder/{w['donor']}?format=csv").text)
    assert got[1][1] == "'=cmd|' /C calc'!A0"
    assert [x[5] for x in got if x[0] == "outcome"] == ['\'=HYPERLINK("x")']
    for line in got[1:]:
        assert not any(cell[:1] in "=+-@" for cell in line if cell)


def test_html_escapes_every_value(db: Session) -> None:
    w = world(db, donor_name="<script>alert(1)</script>")
    r = login("diana").get(f"/api/app/reports/funder/{w['donor']}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<script>" not in r.text and "&lt;script&gt;" in r.text
    assert "750.00" in r.text and "kids" in r.text


def test_contact_and_notes_only_for_the_owner(db: Session) -> None:
    w = world(db)
    owner = login("diana").get(f"/api/app/reports/funder/{w['donor']}?format=csv").text
    other = login("sam").get(f"/api/app/reports/funder/{w['donor']}?format=csv").text
    for secret in ("grants@acme.example", "+15551230000", "Prefers calls"):
        assert secret in owner
        assert secret not in other


def test_every_export_writes_an_audit_entry_without_contact_details(db: Session) -> None:
    w = world(db)
    login("sam").get(f"/api/app/reports/funder/{w['donor']}?format=csv")
    login("diana").get(f"/api/app/reports/funder/{w['donor']}")
    got = db.execute(
        text("SELECT entity_id, data::text FROM audit_log WHERE action = 'report.funder_export'")
    ).all()
    assert len(got) == 2 and all(g[0] == w["donor"] for g in got)
    assert not any("acme" in g[1] for g in got)


def test_missing_donor_and_bad_dates_are_refused(db: Session) -> None:
    w = world(db)
    c = login("sam")
    assert c.get("/api/app/reports/funder/99999").status_code == 404
    assert (
        c.get(f"/api/app/reports/funder/{w['donor']}?from=2026-02-01&to=2026-01-01").status_code
        == 400
    )
    assert c.get(f"/api/app/reports/funder/{w['donor']}?format=xml").status_code in (400, 422)
    assert TestClient(create_app()).get(f"/api/app/reports/funder/{w['donor']}").status_code == 401
