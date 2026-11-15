"""Log a contact, set and complete a next step (DON-4, DON-9, DON-10).
Includes the 403 half of acceptance test 7: acting on another member's donor is refused."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)  # Sun 09:00 in Phoenix
PW = "correct horse battery"


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    zelda = seed.add_donor(db, "Zelda Quill", owner=diana, email="zelda@pii.test")
    nia = seed.add_donor(db, "Nia Newbie", owner=sam)
    gone = seed.add_donor(db, "Gone Gary", owner=diana, deleted=True)
    db.commit()
    return dict(diana=diana, sam=sam, zelda=zelda, nia=nia, gone=gone)


def login(email: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    assert c.post("/api/app/auth/login", json={"email": email, "password": PW}).status_code == 200
    return c


def h(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}


def post(c: TestClient, path: str, body: dict | None = None):
    return c.post(f"/api/app{path}", json=body, headers=h(c))


def put(c: TestClient, path: str, body: dict):
    return c.put(f"/api/app{path}", json=body, headers=h(c))


def timeline(c: TestClient, donor: int) -> list[dict]:
    return c.get(f"/api/app/donors/{donor}/timeline").json()["items"]


# --- log a contact ---------------------------------------------------------------------------
def test_owner_logs_a_contact_that_shows_on_the_timeline(w) -> None:
    c = login("diana@example.org")
    r = post(
        c, f"/donors/{w['zelda']}/interactions", {"kind": "call", "summary": "Left a voicemail"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "call" and body["summary"] == "Left a voicemail"
    assert body["occurred_on"] == "2026-11-15"  # defaults to today in Phoenix
    assert body["user"]["display_name"] == "Diana" and body["donor_id"] == w["zelda"]
    top = timeline(c, w["zelda"])[0]
    assert (top["kind"], top["title"], top["detail"], top["by"]) == (
        "contact", "Call", "Left a voicemail", "Diana",
    )  # fmt: skip
    card = c.get(f"/api/app/donors/{w['zelda']}").json()
    assert card["last_contact_date"] == "2026-11-15"


# --- acceptance test 7 (acting half) ----------------------------------------------------------
def test_other_member_cannot_act_on_a_donor_they_do_not_own(db: Session, w) -> None:
    sam = login("sam@example.org")
    assert sam.get(f"/api/app/donors/{w['zelda']}").status_code == 200  # may look
    for r in (
        post(sam, f"/donors/{w['zelda']}/interactions", {"kind": "call"}),
        put(sam, f"/donors/{w['zelda']}/next-step", {"title": "x", "due_date": "2026-12-01"}),
    ):
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "forbidden"
    login("diana@example.org")  # nothing was written
    n = db.execute(text("SELECT count(*) FROM interactions")).scalar_one()
    steps = db.execute(text("SELECT count(*) FROM next_steps")).scalar_one()
    assert (n, steps) == (0, 0)


# --- next step -------------------------------------------------------------------------------
def test_set_next_step_shows_on_card_and_timeline(w) -> None:
    c = login("diana@example.org")
    r = put(
        c, f"/donors/{w['zelda']}/next-step", {"title": "Invite to camp", "due_date": "2026-12-01"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "open" and r.json()["due_date"] == "2026-12-01"
    d = c.get(f"/api/app/donors/{w['zelda']}").json()
    assert (d["next_step_title"], d["next_step_due"]) == ("Invite to camp", "2026-12-01")
    assert timeline(c, w["zelda"])[0]["title"] == "Next step: Invite to camp"


def test_setting_a_new_step_replaces_the_open_one(db: Session, w) -> None:
    c = login("diana@example.org")
    first = put(
        c, f"/donors/{w['zelda']}/next-step", {"title": "A", "due_date": "2026-12-01"}
    ).json()
    second = put(
        c, f"/donors/{w['zelda']}/next-step", {"title": "B", "due_date": "2026-12-05"}
    ).json()
    assert first["id"] != second["id"]
    rows = db.execute(text("SELECT title, status FROM next_steps ORDER BY id")).all()
    assert rows == [("A", "cancelled"), ("B", "open")]  # one open step; history kept
    assert c.get(f"/api/app/donors/{w['zelda']}").json()["next_step_title"] == "B"


def test_completing_a_step_logs_an_interaction_and_clears_the_card(
    db: Session, w, clock: FixedClock
) -> None:
    c = login("diana@example.org")
    step = put(
        c, f"/donors/{w['zelda']}/next-step", {"title": "Send update", "due_date": "2026-11-20"}
    ).json()
    clock.at += timedelta(hours=1)  # completing happens after creating, on the app clock
    r = post(c, f"/next-steps/{step['id']}/done")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done" and r.json()["done_at"] is not None
    d = c.get(f"/api/app/donors/{w['zelda']}").json()
    assert d["next_step_title"] is None and d["last_contact_date"] == "2026-11-15"
    top = timeline(c, w["zelda"])[0]
    assert (top["kind"], top["detail"], top["by"]) == (
        "note",
        "Completed next step: Send update",
        "Diana",
    )
    # a new step can be set afterwards
    assert (
        put(
            c, f"/donors/{w['zelda']}/next-step", {"title": "Next", "due_date": "2026-12-01"}
        ).status_code
        == 200
    )


# --- audit (issue #88) -----------------------------------------------------------------------
def audit_rows(db: Session) -> list[tuple[str, str | None, int | None, dict]]:
    db.expire_all()
    rows = db.execute(
        text("SELECT action, entity, entity_id, data FROM audit_log WHERE action LIKE '%.%' "
             "AND action NOT LIKE 'auth.%' ORDER BY id")
    ).all()  # fmt: skip
    return [tuple(r) for r in rows]  # type: ignore[misc]


def test_each_action_writes_one_audit_entry_with_ids_only(db: Session, w) -> None:
    c = login("diana@example.org")
    secret = "Mrs Quill's phone is 555-0100"
    contact = post(
        c, f"/donors/{w['zelda']}/interactions", {"kind": "call", "summary": secret}
    ).json()
    step = put(
        c, f"/donors/{w['zelda']}/next-step", {"title": secret, "due_date": "2026-12-01"}
    ).json()
    post(c, f"/next-steps/{step['id']}/done")
    assert audit_rows(db) == [
        ("interaction.create", "interaction", contact["id"],
         {"donor_id": w["zelda"], "kind": "call"}),
        ("next_step.set", "next_step", step["id"], {"donor_id": w["zelda"]}),
        ("next_step.done", "next_step", step["id"], {"donor_id": w["zelda"]}),
    ]  # fmt: skip
    assert secret not in str(audit_rows(db))
    who = db.execute(
        text("SELECT DISTINCT actor_kind, actor_id FROM audit_log WHERE action LIKE '%.%'"
             " AND action NOT LIKE 'auth.%'")
    ).all()  # fmt: skip
    assert [tuple(r) for r in who] == [("user", w["diana"])]
