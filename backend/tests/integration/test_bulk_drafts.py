# ruff: noqa: F811 (the fixtures come from tests.msgkit and are used as arguments)
"""Draft quarterly updates in bulk (MSG-2): mine only, idempotent, skips do-not-contact."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from tests import seed
from tests.msgkit import clock, login, post, w  # noqa: F401


def test_bulk_drafts_cover_my_due_donors_once(db: Session, w) -> None:
    # Zelda (mine) and Nia (Sam's) have no contact for 90+ days; Dan is do-not-contact.
    dan = seed.add_donor(db, "Dan Quiet", owner=w["diana"], email="dan@pii.test")
    db.execute(text("UPDATE donors SET do_not_contact = true WHERE id = :d"), {"d": dan})
    db.execute(text("UPDATE donors SET created_at = '2026-01-01', email = 'n@pii.test'"))
    db.commit()
    c = login("diana.owner@example.org")
    first = post(c, "/messages/draft-quarterly")
    assert first.status_code == 200, first.text
    out = first.json()
    assert out["created"] == 1 and out["skipped_existing"] == 0
    assert [m["donor_name"] for m in out["messages"]] == ["Zelda Quill"]  # not Nia, not Dan
    assert (
        out["messages"][0]["kind"] == "quarterly_update" and out["messages"][0]["status"] == "draft"
    )
    again = post(c, "/messages/draft-quarterly").json()
    assert again["created"] == 0 and again["skipped_existing"] == 1
    assert db.execute(text("SELECT count(*) FROM messages")).scalar_one() == 1
