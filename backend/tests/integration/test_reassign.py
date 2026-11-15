"""Manual and bulk reassignment with owner history (OWN-3, OWN-4, D-105, D-123).
Acceptance test 5 (manual reassignment shows in history) and the 403 half of test 6."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed

NOW = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(NOW)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    diana, sam, alex = (seed.add_user(db, n) for n in ("Diana", "Sam", "Alex"))
    gone = seed.add_user(db, "Gone Gail", active=False)
    d_sam = seed.add_donor(db, "Sam Donor", owner=sam)
    d_alex = seed.add_donor(db, "Alex Donor", owner=alex)
    d_gone = seed.add_donor(db, "Orphan Ola", owner=gone)
    db.commit()
    return dict(
        diana=diana, sam=sam, alex=alex, gone=gone, d_sam=d_sam, d_alex=d_alex, d_gone=d_gone
    )


def login(name: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{name}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    return c


def post(c: TestClient, path: str, body: dict):
    return c.post(f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies.get("cic_csrf")})


def make_super_admin(db: Session, user: int, scope: str = "own_only") -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active', "
             "reassign_scope = :s WHERE id = 1"),
        {"u": user, "s": scope},
    )  # fmt: skip
    db.commit()


def test_flat_mode_any_member_reassigns_and_history_records_it(db: Session, w) -> None:
    """Acceptance 5: manual reassignment of an orphaned donor, visible in owner history."""
    diana = login("diana")
    r = post(
        diana, f"/donors/{w['d_gone']}/reassign", {"to_user_id": w["diana"], "reason": "Gail left"}
    )
    assert r.status_code == 200 and r.json()["owner"]["id"] == w["diana"]
    history = login("alex").get(f"/api/app/donors/{w['d_gone']}/owner-history").json()["items"]
    assert len(history) == 1
    top = history[0]
    assert (top["method"], top["reason"]) == ("manual", "Gail left")
    assert top["from_user"]["id"] == w["gone"] and top["to_user"]["id"] == w["diana"]
    assert top["changed_by"]["id"] == w["diana"]
    audit = db.execute(text("SELECT action FROM audit_log WHERE action = 'donor.reassign'")).all()
    assert len(audit) == 1
    # Hand-offs count for the round-robin tie-break (D-132).
    stamp = db.execute(text("SELECT last_assigned_at FROM users WHERE id = :u"), {"u": w["diana"]})
    assert stamp.scalar_one() == NOW


def test_target_must_be_active_and_different(db: Session, w) -> None:
    sam = login("sam")
    assert post(sam, f"/donors/{w['d_sam']}/reassign", {"to_user_id": w["gone"]}).status_code == 400
    assert post(sam, f"/donors/{w['d_sam']}/reassign", {"to_user_id": w["sam"]}).status_code == 409
    assert post(sam, "/donors/99999/reassign", {"to_user_id": w["alex"]}).status_code == 404


def test_own_only_blocks_other_members_donors_until_flattened(db: Session, w) -> None:
    """Acceptance 6 (403 half): own_only with an active super admin."""
    make_super_admin(db, w["diana"])
    sam = login("sam")
    denied = post(sam, f"/donors/{w['d_alex']}/reassign", {"to_user_id": w["sam"]})
    assert denied.status_code == 403
    own = post(sam, f"/donors/{w['d_sam']}/reassign", {"to_user_id": w["alex"]})
    assert own.status_code == 200
    # A deactivated member's donors: only the super admin may move them (D-123).
    assert post(sam, f"/donors/{w['d_gone']}/reassign", {"to_user_id": w["sam"]}).status_code == 403
    sa = post(login("diana"), f"/donors/{w['d_gone']}/reassign", {"to_user_id": w["sam"]})
    assert sa.status_code == 200
    unchanged = db.execute(
        text("SELECT owner_user_id FROM donors WHERE id = :d"), {"d": w["d_alex"]}
    )
    assert unchanged.scalar_one() == w["alex"]


def test_bulk_move_is_super_admin_only_and_records_each_donor(db: Session, w) -> None:
    make_super_admin(db, w["diana"])
    seed.add_donor(db, "Second Gail Donor", owner=w["gone"])
    seed.add_donor(db, "Deleted Gail Donor", owner=w["gone"], deleted=True)
    db.commit()
    body = {"to_user_id": w["alex"]}
    assert post(login("sam"), f"/members/{w['gone']}/move-donors", body).status_code == 403
    assert (
        post(
            login("diana"), f"/members/{w['gone']}/move-donors", {"to_user_id": w["gone"]}
        ).status_code
        == 400
    )
    r = post(login("diana"), f"/members/{w['gone']}/move-donors", body)
    assert r.status_code == 200 and r.json() == {"moved": 2}
    rows = db.execute(text("SELECT method FROM owner_history WHERE method = 'bulk'")).all()
    assert len(rows) == 2
    assert (
        db.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'donor.bulk_move'")
        ).scalar_one()
        == 1
    )  # one audit entry per bulk move
    sql = "SELECT count(*) FROM donors WHERE owner_user_id = :g AND deleted_at IS NULL"
    left = db.execute(text(sql), {"g": w["gone"]}).scalar_one()
    assert left == 0


def test_logged_out_is_refused(db: Session, w) -> None:
    anon = TestClient(create_app())
    assert anon.get(f"/api/app/donors/{w['d_sam']}/owner-history").status_code == 401
