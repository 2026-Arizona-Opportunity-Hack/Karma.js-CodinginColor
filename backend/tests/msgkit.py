"""Shared setup for the message tests: a clock, two members, a donor with gifts, API helpers."""

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


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    """Diana owns Zelda (email, phone, one gift, one employer match); Sam owns Nia."""
    diana, sam = seed.add_user(db, "Diana Owner"), seed.add_user(db, "Sam Other")
    zelda = seed.add_donor(
        db, "Zelda Quill", owner=diana, email="zelda@pii.test", phone="+15550100"
    )
    gift = seed.add_gift(db, zelda, date(2026, 11, 3), 5000, program="AI Academy")
    match = seed.add_gift(db, zelda, date(2026, 11, 3), 5000)
    db.execute(text("UPDATE gifts SET is_matching_gift = true WHERE id = :g"), {"g": match})
    nia = seed.add_donor(db, "Nia Newbie", owner=sam)
    db.commit()
    return dict(diana=diana, sam=sam, zelda=zelda, gift=gift, match=match, nia=nia)


def login(email: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    assert c.post("/api/app/auth/login", json={"email": email, "password": PW}).status_code == 200
    return c


def _h(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}


def post(c: TestClient, path: str, body: dict | None = None):
    return c.post(f"/api/app{path}", json=body, headers=_h(c))


def patch(c: TestClient, path: str, body: dict):
    return c.patch(f"/api/app{path}", json=body, headers=_h(c))


def make_super_admin(db: Session, user: int, state: str = "active") -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = :s WHERE id = 1"),
        {"u": user, "s": state},
    )
    db.commit()


def draft(
    c: TestClient, w: dict, *, channel: str = "email", text_body: str | None = "Hello Zelda"
) -> dict:
    """A thank-you draft for Zelda's gift, with its words replaced so it can be approved."""
    r = post(
        c, f"/donors/{w['zelda']}/messages",
        {"kind": "thank_you", "channel": channel, "gift_id": w["gift"]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    m = r.json()
    if text_body is not None:
        m = patch(c, f"/messages/{m['id']}", {"body": text_body}).json()
    return m


def row(db: Session, message_id: int) -> dict:
    return dict(
        db.execute(text("SELECT * FROM messages WHERE id = :i"), {"i": message_id}).mappings().one()
    )
