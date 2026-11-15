"""Lapsed-donor radar (issue #41, SRS 3.2 item 1): per-owner list, drafted nudges, MSG-2 and
MSG-8, and acceptance test 11 repeated through the real importer."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed
from tests.integration.test_import_commit import M, commit, preview, world  # noqa: F401

PREV = date(2025, 3, 1)  # inside the previous 12 months as of 2026-11-15
RECENT = date(2026, 6, 1)


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


def post(c: TestClient, path: str, body: dict | None = None):
    return c.post(f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies["cic_csrf"]})


def scene(db: Session) -> dict[str, int]:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    ids = dict(
        diana=diana,
        sam=sam,
        ann=seed.add_donor(db, "Ann Lapsed", owner=diana, email="ann@example.org"),
        bob=seed.add_donor(db, "Bob Texter", owner=diana, phone="+15550001111"),
        cy=seed.add_donor(db, "Cy Optout", owner=diana, email="cy@example.org"),
        dee=seed.add_donor(db, "Dee Active", owner=diana, email="dee@example.org"),
        eve=seed.add_donor(db, "Eve Matchonly", owner=diana, email="eve@example.org"),
        fay=seed.add_donor(db, "Fay Sams", owner=sam, email="fay@example.org"),
    )
    for name in ("ann", "bob", "cy", "fay"):
        seed.add_gift(db, ids[name], PREV, 10_000)
    seed.add_gift(db, ids["dee"], PREV, 5_000)
    seed.add_gift(db, ids["dee"], RECENT, 5_000)  # gave again: not lapsed
    match = seed.add_gift(db, ids["eve"], PREV, 9_000)
    db.execute(text("UPDATE gifts SET is_matching_gift = true WHERE id = :g"), {"g": match})
    db.execute(text("UPDATE donors SET do_not_contact = true WHERE id = :d"), {"d": ids["cy"]})
    db.commit()
    return ids


def test_lists_lapsed_donors_per_owner_without_opt_outs_or_employer_matches(db: Session) -> None:
    ids = scene(db)
    body = login("sam").get("/api/app/reports/lapsed").json()
    got = {o["owner_name"]: [d["display_name"] for d in o["donors"]] for o in body["owners"]}
    assert got == {"Diana": ["Ann Lapsed", "Bob Texter"], "Sam": ["Fay Sams"]}
    assert body["total"] == 3 and body["as_of"] == "2026-11-15"
    ann = body["owners"][0]["donors"][0]
    assert (ann["donor_id"], ann["last_gift_date"], ann["cents_prev"]) == (
        ids["ann"], "2025-03-01", 10_000
    )  # fmt: skip


def test_drafting_nudges_only_for_my_reachable_donors_and_is_idempotent(db: Session) -> None:
    ids = scene(db)
    diana = login("diana")
    first = post(diana, "/reports/lapsed/draft").json()
    assert first["created"] == 2 and first["skipped_existing"] == 0  # Ann (email), Bob (text)
    channels = {m["donor_id"]: m["channel"] for m in first["messages"]}
    assert channels == {ids["ann"]: "email", ids["bob"]: "sms"}
    assert all(m["status"] == "draft" and m["kind"] == "lapsed_nudge" for m in first["messages"])
    assert "Ann" in next(m["body"] for m in first["messages"] if m["channel"] == "email")
    again = post(diana, "/reports/lapsed/draft").json()
    assert (again["created"], again["skipped_existing"]) == (0, 2)  # MSG-2
    n = db.execute(text("SELECT count(*) FROM messages WHERE kind = 'lapsed_nudge'")).scalar_one()
    assert n == 2  # nothing for Cy (do not contact, MSG-8) or for Sam's donor Fay


def test_the_list_shows_the_open_draft_and_no_message_is_sent(db: Session) -> None:
    scene(db)
    diana = login("diana")
    post(diana, "/reports/lapsed/draft")
    donors = diana.get("/api/app/reports/lapsed").json()["owners"][0]["donors"]
    assert all(d["draft_message_id"] for d in donors)
    statuses = db.execute(text("SELECT DISTINCT status FROM messages")).scalars().all()
    assert statuses == ["draft"]  # a human still has to approve and send


def test_a_member_cannot_draft_for_someone_elses_lapsed_donor_and_dnc_is_refused(
    db: Session,
) -> None:
    ids = scene(db)
    sam = login("sam")
    nudge = {"kind": "lapsed_nudge", "channel": "email"}
    other = post(sam, f"/donors/{ids['ann']}/messages", nudge)
    assert other.status_code == 403
    owner = login("diana")
    dnc = post(owner, f"/donors/{ids['cy']}/messages", nudge)
    assert dnc.status_code == 409


def test_the_radar_needs_a_session_and_a_valid_date(db: Session) -> None:
    scene(db)
    assert TestClient(create_app()).get("/api/app/reports/lapsed").status_code == 401
    assert login("sam").get("/api/app/reports/lapsed?as_of=soon").status_code in (400, 422)


def test_real_importer_lapsed_radar_matches_the_manifest_acceptance_11(world, db) -> None:  # noqa: F811
    for source, filename in zip(
        ["spreadsheet", "zeffy", "benevity", "generic"], M["import_order"], strict=True
    ):
        from tests.integration.test_import_commit import FIX

        commit(world, preview(world, (FIX / filename).read_bytes(), source, filename))
    retention = world["client"].get("/api/app/reports/retention?as_of=2026-11-15").json()
    assert retention["classes"] == M["retention"]["classes"]
    radar = world["client"].get("/api/app/reports/lapsed?as_of=2026-11-15").json()
    assert radar["total"] == M["retention"]["classes"]["lapsed"]["donors"] == 40
    ids = {d["donor_id"] for o in radar["owners"] for d in o["donors"]}
    assert {d["donor_id"] for d in retention["donors"]["lapsed"]} == ids
