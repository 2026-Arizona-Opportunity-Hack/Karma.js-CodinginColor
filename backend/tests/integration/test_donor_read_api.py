"""Donor list, detail, timeline and unattributed gifts (DON-1 to DON-6, DON-11, D-104)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)  # Sun 09:00 in Phoenix
PW = "correct horse battery"
EMAIL, PHONE, NOTES = "zelda@pii.test", "+15551230000", "likes owls"


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    tom = seed.add_user(db, "Tom", active=False)
    zelda = seed.add_donor(db, "Zelda Quill", owner=diana, email=EMAIL, phone=PHONE, notes=NOTES)
    newbie = seed.add_donor(db, "Nia Newbie", owner=sam, email="nia@pii.test")
    lapsed = seed.add_donor(db, "Larry Lapsed", owner=diana)
    orphaned = seed.add_donor(db, "Olive Orphan", owner=tom)
    dnc = seed.add_donor(db, "Dee Dnc", owner=sam)
    pending = seed.add_donor(db, "Pat Pending", owner=None)
    gone = seed.add_donor(db, "Gone Gary", owner=sam, deleted=True)
    db.execute(text("UPDATE donors SET do_not_contact = true WHERE id = :i"), {"i": dnc})
    seed.add_gift(db, zelda, date(2024, 1, 5), 4_000)
    seed.add_gift(db, zelda, date(2026, 10, 3), 10_000, program="AI Academy")
    g_last = seed.add_gift(db, zelda, date(2026, 11, 10), 5_000, program="Summer Camp")
    seed.add_gift(db, zelda, date(2026, 11, 11), 999, deleted=True)  # not counted
    seed.add_gift(db, newbie, date(2026, 11, 1), 2_500)
    seed.add_gift(db, lapsed, date(2025, 3, 1), 3_000)
    seed.add_gift(db, None, date(2026, 11, 12), 700)  # anonymous
    seed.add_gift(db, None, date(2026, 11, 13), 800, attribution="pending_review")
    seed.add_gift(db, gone, date(2026, 11, 1), 50)
    seed.add_interaction(db, zelda, diana, date(2026, 11, 12), "call")
    seed.add_interaction(db, zelda, diana, date(2026, 11, 13), "note")
    seed.add_interaction(db, zelda, None, date(2026, 11, 14), "system")  # never shown
    seed.add_sent_message(db, zelda, diana, datetime(2026, 11, 14, 20, 0, tzinfo=UTC))
    seed.add_next_step(db, zelda, diana, "Invite to camp", date(2026, 12, 1))
    seed.add_owner_history(db, zelda, diana, at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC))
    db.commit()
    return dict(diana=diana, sam=sam, tom=tom, zelda=zelda, newbie=newbie, lapsed=lapsed,
                orphaned=orphaned, dnc=dnc, pending=pending, gone=gone, g_last=g_last)  # fmt: skip


def login(db_email: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post("/api/app/auth/login", json={"email": db_email, "password": PW})
    assert r.status_code == 200, r.text
    return c


def diana() -> TestClient:
    return login("diana@example.org")


def sam() -> TestClient:
    return login("sam@example.org")


def names(r) -> list[str]:
    return [i["display_name"] for i in r.json()["items"]]


def test_logged_out_gets_401() -> None:
    c = TestClient(create_app())
    for path in ("/donors", "/donors/1", "/donors/1/timeline", "/gifts/unattributed"):
        assert c.get(f"/api/app{path}").status_code == 401, path


def test_default_is_my_donors_and_all_shows_everyone(w) -> None:
    c = diana()
    assert names(c.get("/api/app/donors")) == ["Larry Lapsed", "Zelda Quill"]
    everyone = c.get("/api/app/donors", params={"scope": "all"})
    assert names(everyone) == [
        "Dee Dnc", "Larry Lapsed", "Nia Newbie", "Olive Orphan", "Pat Pending", "Zelda Quill",
    ]  # fmt: skip
    assert everyone.json()["total"] == 6  # the deleted donor is not listed


def test_card_totals_count_linked_gifts_only(w) -> None:
    card = next(
        i
        for i in diana().get("/api/app/donors").json()["items"]
        if i["display_name"] == "Zelda Quill"
    )
    assert card["total_12m_cents"] == 15_000  # 10,000 + 5,000; deleted gift excluded
    assert card["total_lifetime_cents"] == 19_000
    assert card["last_gift_date"] == "2026-11-10"
    assert card["last_contact_date"] == "2026-11-13"  # system entries do not count
    assert (card["next_step_title"], card["next_step_due"]) == ("Invite to camp", "2026-12-01")
    assert card["owner"] == {"id": w["diana"], "display_name": "Diana", "is_active": True}
    assert [g["gross_cents"] for g in card["recent_gifts"]] == [5_000, 10_000, 4_000]
    assert "email" not in card and "phone" not in card


def test_owner_program_and_name_filters(w) -> None:
    c = diana()
    assert names(c.get("/api/app/donors", params={"scope": "all", "owner": w["sam"]})) == [
        "Dee Dnc",
        "Nia Newbie",
    ]
    camp = c.get("/api/app/donors", params={"scope": "all", "program": 3})
    assert names(camp) == ["Zelda Quill"]  # Summer Camp is program 3
    assert names(c.get("/api/app/donors", params={"scope": "all", "q": "larry"})) == [
        "Larry Lapsed"
    ]


def test_searching_by_email_only_works_where_contact_is_visible(w) -> None:
    owner_hit = diana().get("/api/app/donors", params={"scope": "all", "q": "zelda@pii"})
    assert names(owner_hit) == ["Zelda Quill"]
    other = sam().get("/api/app/donors", params={"scope": "all", "q": "zelda@pii"})
    assert names(other) == []  # an email search must not confirm another member's donor email


# --- acceptance test 7 (reads): another member sees history but not contact details ---------
def test_owner_sees_contact_details(w) -> None:
    d = diana().get(f"/api/app/donors/{w['zelda']}").json()
    assert (d["email"], d["phone"], d["notes"]) == (EMAIL, PHONE, NOTES)
    assert d["contact_visible"] is True and d["contact_via"] is None
    assert d["can_act"] is True and d["can_reassign"] is True


def test_other_member_sees_history_but_not_contact_details(w) -> None:
    r = sam().get(f"/api/app/donors/{w['zelda']}")
    assert r.status_code == 200
    d = r.json()
    assert (d["email"], d["phone"], d["notes"]) == (None, None, None)
    assert d["contact_visible"] is False and d["contact_via"] == "Diana"
    assert d["can_act"] is False
    assert d["can_reassign"] is True  # flat mode: scope `anyone`
    assert d["total_lifetime_cents"] == 19_000 and len(d["recent_gifts"]) == 3
    for secret in (EMAIL, PHONE, NOTES):
        assert secret not in r.text
    assert sam().get(f"/api/app/donors/{w['zelda']}/timeline").status_code == 200


def test_timeline_mixes_everything_newest_first(w) -> None:
    items = sam().get(f"/api/app/donors/{w['zelda']}/timeline").json()["items"]
    ats = [i["at"] for i in items]
    assert ats == sorted(ats, reverse=True)
    kinds = {i["kind"] for i in items}
    assert kinds == {"gift", "contact", "note", "message", "next_step", "owner_change"}
    gift = next(i for i in items if i["entity_id"] == w["g_last"] and i["kind"] == "gift")
    assert gift["amount_cents"] == 5_000
    assert not any(i["title"] == "System" for i in items)  # system entries are hidden
    assert all("body" not in i for i in items)  # message bodies never appear


def test_unattributed_lists_anonymous_and_pending_review_only(w) -> None:
    items = diana().get("/api/app/gifts/unattributed").json()["items"]
    assert [(i["attribution"], i["gross_cents"], i["donor_name"]) for i in items] == [
        ("pending_review", 800, None),
        ("anonymous", 700, None),
    ]
    assert all(i["donor_id"] is None for i in items)
