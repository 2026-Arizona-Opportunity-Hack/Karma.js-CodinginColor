"""Derived reminders (REM-1 to REM-4) with an injected `today`. Acceptance test 8 (reminder half):
a logged contact clears the quarterly reminder."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import CLI
from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from app.services import reminders
from tests import seed

TODAY = date(2026, 11, 15)
OLD = datetime(2026, 1, 1, tzinfo=UTC)  # a donor created long ago


def day(n: int) -> date:
    return date(2026, 11, n)


def old_donor(db: Session, name: str, owner: int | None) -> int:
    d = seed.add_donor(db, name, owner=owner)
    db.execute(text("UPDATE donors SET created_at = :t WHERE id = :d"), {"t": OLD, "d": d})
    return d


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(datetime(2026, 11, 15, 16, 0, tzinfo=UTC))
    set_clock(c)
    yield c
    set_clock(SystemClock())


def test_thank_you_is_due_two_days_after_a_first_gift_and_seven_after_a_repeat(db: Session):
    me = seed.add_user(db, "Diana")
    a = old_donor(db, "Repeat Rita", me)
    seed.add_gift(db, a, date(2026, 11, 1), 1000)  # first gift, thanked long ago
    db.execute(text("UPDATE gifts SET assumed_thanked = TRUE WHERE donor_id = :d"), {"d": a})
    repeat_due = seed.add_gift(db, a, day(10), 1000)  # repeat: due 17th, inside today + 2
    repeat_later = seed.add_gift(db, a, day(11), 1000)  # repeat: due 18th, not yet shown
    b = old_donor(db, "Brand New Bea", me)
    first_due = seed.add_gift(db, b, day(15), 1000)  # first: due 17th, shown
    c = old_donor(db, "Later Lou", me)
    first_later = seed.add_gift(db, c, day(16), 1000)  # first: due 18th, not yet shown
    db.commit()

    shown = {r.gift_id: r for r in reminders.todo_for(db, CLI, TODAY, me) if r.gift_id}
    assert set(shown) == {repeat_due, first_due}
    assert repeat_later not in shown and first_later not in shown
    assert shown[first_due].due_date == day(17) and shown[first_due].action == "draft_thank_you"


def test_matching_gifts_deleted_gifts_and_sent_thank_yous_never_show(db: Session):
    me = seed.add_user(db, "Diana")
    d = old_donor(db, "Employee Eve", me)
    match = seed.add_gift(db, d, day(1), 5000)
    db.execute(text("UPDATE gifts SET is_matching_gift = TRUE WHERE id = :g"), {"g": match})
    gone = seed.add_gift(db, d, day(2), 1000, deleted=True)
    thanked = seed.add_gift(db, d, day(3), 1000)
    by_log = seed.add_gift(db, d, day(4), 1000)
    open_one = seed.add_gift(db, d, day(5), 1000)
    msg = seed.add_sent_message(db, d, me, OLD)
    db.execute(text("UPDATE messages SET gift_id = :g, kind = 'thank_you' WHERE id = :m"),
               {"g": thanked, "m": msg})  # fmt: skip
    db.execute(
        text("INSERT INTO interactions (donor_id, kind, occurred_on, gift_id) "
             "VALUES (:d, 'thank_you', :w, :g)"),
        {"d": d, "w": TODAY, "g": by_log},
    )  # fmt: skip
    db.commit()

    due = [r.gift_id for r in reminders.todo_for(db, CLI, TODAY, me) if r.type == "thank_you_due"]
    assert due == [open_one]
    assert match not in due and gone not in due


def test_a_logged_contact_clears_the_quarterly_reminder(db: Session):
    """Acceptance test 8, reminders half."""
    me = seed.add_user(db, "Diana")
    stale = old_donor(db, "Stale Sam", me)
    touched = old_donor(db, "Touched Tia", me)
    seed.add_interaction(db, touched, me, day(1), "call")  # inside 90 days
    fresh = seed.add_donor(db, "Fresh Fay", owner=me)  # created now: no flag on day one
    muted = old_donor(db, "Muted Max", me)
    db.execute(text("UPDATE donors SET do_not_contact = TRUE WHERE id = :d"), {"d": muted})
    db.commit()

    def due() -> set[int]:
        return {r.donor_id for r in reminders.quarterly_due_for(db, CLI, TODAY, me)}

    assert due() == {stale}
    assert fresh not in due() and muted not in due()
    seed.add_interaction(db, stale, me, TODAY, "call")
    db.commit()
    assert due() == set()


def test_next_steps_and_needs_reassignment(db: Session):
    me, gone = seed.add_user(db, "Diana"), seed.add_user(db, "Gone Gail", active=False)
    a, b = old_donor(db, "Soon Sue", me), old_donor(db, "Far Fred", me)
    orphan = old_donor(db, "Orphan Ola", gone)
    soon = seed.add_next_step(db, a, me, "Call", day(18))  # today + 3: shown
    seed.add_next_step(db, b, me, "Call", day(19))  # today + 4: not yet
    db.commit()

    items = reminders.todo_for(db, CLI, TODAY, me)
    steps = [r for r in items if r.type == "next_step_due"]
    assert [r.next_step_id for r in steps] == [soon]
    assert [r.donor_id for r in items if r.type == "needs_reassignment"] == [orphan]
    assert next(r for r in items if r.type == "needs_reassignment").action == "reassign"
    # The inactive owner's donor is not counted for any active member's own work.
    counts = reminders.counts_by_member(db, CLI, TODAY)
    assert set(counts) == {me}
    assert (counts[me].next_step_due, counts[me].needs_reassignment) == (1, 1)


def test_reminders_api_returns_mine_plus_orphans_for_everyone(db: Session, clock: FixedClock):
    me, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    gone = seed.add_user(db, "Gone Gail", active=False)
    mine = old_donor(db, "Mine Mia", me)
    old_donor(db, "Sam Sally", sam)
    orphan = old_donor(db, "Orphan Ola", gone)
    db.commit()

    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    login = c.post(
        "/api/app/auth/login", json={"email": "diana@example.org", "password": seed.PASSWORD}
    )
    assert login.status_code == 200
    items = c.get("/api/app/reminders").json()["items"]
    assert [(i["type"], i["donor_id"]) for i in items] == [
        ("quarterly_due", mine),
        ("needs_reassignment", orphan),
    ]
    listed = c.get("/api/app/reminders/needs-reassignment").json()["items"]
    assert [i["donor_id"] for i in listed] == [orphan]
    assert TestClient(create_app()).get("/api/app/reminders").status_code == 401
