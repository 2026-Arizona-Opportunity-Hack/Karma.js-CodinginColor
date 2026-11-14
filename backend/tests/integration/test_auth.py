from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.actor import CLI
from app.clock import FixedClock, SystemClock, set_clock
from app.db.models import AuditLog, SessionRow
from app.main import create_app
from app.repos import users
from app.security import hash_password

PW = "correct horse battery"
T0 = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def members(db: Session) -> dict[str, int]:
    out = {}
    for email, name in [("diana@example.org", "Diana"), ("sam@example.org", "Sam")]:
        u = users.create(db, CLI, email=email, display_name=name, password_hash=hash_password(PW))
        out[email] = u.id
    db.commit()
    return out


def client(ip: str = "203.0.113.5") -> TestClient:
    return TestClient(create_app(), client=(ip, 50000))


def login(c: TestClient, email: str, password: str = PW) -> int:
    return c.post("/api/app/auth/login", json={"email": email, "password": password}).status_code


def csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}


def test_logged_out_calls_get_401(db: Session, clock: FixedClock) -> None:
    c = client()
    assert c.get("/api/app/auth/me").status_code == 401
    assert c.post("/api/app/auth/logout").status_code == 401


def test_two_members_log_in_separately(db: Session, clock: FixedClock, members) -> None:
    a, b = client(), client()
    assert login(a, "diana@example.org") == 200
    assert login(b, "SAM@example.org ") == 200  # case and spaces ignored
    assert a.get("/api/app/auth/me").json()["display_name"] == "Diana"
    me_b = b.get("/api/app/auth/me").json()
    assert me_b["display_name"] == "Sam"
    assert me_b["is_super_admin"] is False
    assert me_b["governance"] == {"mode": "flat", "reassign_scope": "anyone"}


def test_session_token_is_stored_hashed(db: Session, clock: FixedClock, members) -> None:
    c = client()
    login(c, "diana@example.org")
    token = c.cookies.get("cic_session")
    stored = db.execute(select(SessionRow.token_hash)).scalars().all()
    assert token and token not in stored and len(stored) == 1


def test_wrong_password_and_unknown_email_look_the_same(
    db: Session, clock: FixedClock, members
) -> None:
    c = client()
    r1 = c.post("/api/app/auth/login", json={"email": "diana@example.org", "password": "nope"})
    r2 = c.post("/api/app/auth/login", json={"email": "who@example.org", "password": "nope"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_rate_limit_per_email(db: Session, clock: FixedClock, members) -> None:
    c = client()
    for _ in range(5):
        assert login(c, "diana@example.org", "bad") == 401
    assert login(c, "diana@example.org") == 429  # even the right password
    clock.at = T0 + timedelta(minutes=16)
    assert login(c, "diana@example.org") == 200


def test_rate_limit_per_ip(db: Session, clock: FixedClock, members) -> None:
    c = client()
    for i in range(5):
        login(c, f"nobody{i}@example.org", "bad")
    assert login(c, "sam@example.org") == 429


def test_state_change_needs_csrf_token(db: Session, clock: FixedClock, members) -> None:
    c = client()
    login(c, "diana@example.org")
    assert c.post("/api/app/auth/logout").status_code == 403
    assert c.post("/api/app/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert c.post("/api/app/auth/logout", headers=csrf(c)).status_code == 204
    assert c.get("/api/app/auth/me").status_code == 401


def test_logout_revokes_the_session_server_side(db: Session, clock: FixedClock, members) -> None:
    c = client()
    login(c, "diana@example.org")
    stolen = c.cookies.get("cic_session")
    c.post("/api/app/auth/logout", headers=csrf(c))
    thief = client()
    thief.cookies.set("cic_session", stolen or "")
    assert thief.get("/api/app/auth/me").status_code == 401


def test_idle_and_absolute_expiry(db: Session, clock: FixedClock, members) -> None:
    c = client()
    login(c, "diana@example.org")
    for hours in range(10, 7 * 24, 10):  # active every 10 h stays logged in (last: 160 h)
        clock.at = T0 + timedelta(hours=hours)
        assert c.get("/api/app/auth/me").status_code == 200
    clock.at = T0 + timedelta(days=7)
    assert c.get("/api/app/auth/me").status_code == 401

    c2 = client()
    login(c2, "sam@example.org")
    clock.at += timedelta(hours=12, minutes=1)
    assert c2.get("/api/app/auth/me").status_code == 401


def test_deactivated_member_cannot_log_in_and_loses_sessions(
    db: Session, clock: FixedClock, members
) -> None:
    c = client()
    login(c, "sam@example.org")
    sam = users.get_for_session(db, members["sam@example.org"])
    assert sam is not None
    users.set_active(db, CLI, sam, False, clock.now())
    db.commit()
    assert c.get("/api/app/auth/me").status_code == 401
    assert login(client(), "sam@example.org") == 401


def test_logins_are_audited(db: Session, clock: FixedClock, members) -> None:
    c = client()
    login(c, "diana@example.org", "bad")
    login(c, "diana@example.org")
    actions = db.execute(select(AuditLog.action).order_by(AuditLog.id)).scalars().all()
    assert actions == ["auth.login_failed", "auth.login"]
