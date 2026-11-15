"""Governance scope and flatten from the app (GOV-4, GOV-5, GOV-7).
Acceptance test 6: with own_only a member cannot reassign another member's donor (403);
after Flatten they can."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(datetime(2026, 11, 15, 16, 0, tzinfo=UTC))
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    diana, sam, alex = (seed.add_user(db, n) for n in ("Diana", "Sam", "Alex"))
    donor = seed.add_donor(db, "Alex Donor", owner=alex)
    db.commit()
    return dict(diana=diana, sam=sam, alex=alex, donor=donor)


def login(name: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{name}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    return c


def send(c: TestClient, method: str, path: str, body: dict | None = None):
    return c.request(
        method, f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies.get("cic_csrf")}
    )


def make_super_admin(db: Session, user: int) -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
             "WHERE id = 1"),
        {"u": user},
    )  # fmt: skip
    db.commit()


def test_any_member_can_read_governance(db: Session, w) -> None:
    flat = login("sam").get("/api/app/governance").json()
    assert (flat["mode"], flat["super_admin_state"], flat["reassign_scope"]) == (
        "flat",
        "none",
        "anyone",
    )
    make_super_admin(db, w["diana"])
    active = login("sam").get("/api/app/governance").json()
    assert active["mode"] == "super_admin" and active["super_admin"]["id"] == w["diana"]
    assert TestClient(create_app()).get("/api/app/governance").status_code == 401


def test_only_the_active_super_admin_sets_the_scope_and_it_is_audited(db: Session, w) -> None:
    assert (
        send(login("sam"), "PUT", "/governance/scope", {"reassign_scope": "own_only"}).status_code
        == 403
    )
    assert (
        send(login("diana"), "PUT", "/governance/scope", {"reassign_scope": "own_only"}).status_code
        == 403
    )  # flat
    make_super_admin(db, w["diana"])
    assert (
        send(login("sam"), "PUT", "/governance/scope", {"reassign_scope": "own_only"}).status_code
        == 403
    )
    sa = login("diana")
    r = send(sa, "PUT", "/governance/scope", {"reassign_scope": "own_only"})
    assert r.status_code == 200 and r.json()["reassign_scope"] == "own_only"
    assert send(sa, "PUT", "/governance/scope", {"reassign_scope": "nobody"}).status_code == 400
    data = db.execute(
        text("SELECT data FROM audit_log WHERE action = 'gov.set_scope'")
    ).scalar_one()
    assert data == {"from": "anyone", "to": "own_only"}


def test_flatten_is_super_admin_only_and_returns_scope_to_anyone(db: Session, w) -> None:
    make_super_admin(db, w["diana"])
    sa = login("diana")
    send(sa, "PUT", "/governance/scope", {"reassign_scope": "own_only"})
    assert send(login("sam"), "POST", "/governance/flatten").status_code == 403
    r = send(sa, "POST", "/governance/flatten")
    assert r.status_code == 200
    assert (r.json()["mode"], r.json()["super_admin_state"], r.json()["reassign_scope"]) == (
        "flat", "dormant", "anyone",
    )  # fmt: skip
    assert send(sa, "POST", "/governance/flatten").status_code == 403  # no longer active
    assert (
        db.execute(text("SELECT count(*) FROM audit_log WHERE action = 'gov.flatten'")).scalar_one()
        == 1
    )


def test_scope_blocks_a_member_until_the_hierarchy_is_flattened(db: Session, w) -> None:
    """Acceptance 6."""
    make_super_admin(db, w["diana"])
    send(login("diana"), "PUT", "/governance/scope", {"reassign_scope": "own_only"})
    sam = login("sam")
    path = f"/donors/{w['donor']}/reassign"
    assert send(sam, "POST", path, {"to_user_id": w["sam"]}).status_code == 403
    assert send(login("diana"), "POST", "/governance/flatten").status_code == 200
    assert send(login("sam"), "POST", path, {"to_user_id": w["sam"]}).status_code == 200
