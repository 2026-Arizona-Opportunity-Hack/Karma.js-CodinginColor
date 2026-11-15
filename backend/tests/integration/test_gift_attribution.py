"""Attribute anonymous revenue without changing ownership or recording donor contact."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.authz import policy
from app.authz.actor import Actor
from app.clock import FixedClock, SystemClock, set_clock
from app.db.models import AuditLog, Donor, Gift, Interaction, OwnerHistory, User
from app.main import create_app
from app.repos import reports
from tests import seed

NOW = datetime(2026, 11, 15, 16, tzinfo=UTC)


@pytest.fixture
def world(db):
    set_clock(FixedClock(NOW))
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    donor = seed.add_donor(db, "Ada Jones", owner=diana)
    gift = seed.add_gift(db, None, date(2026, 11, 14), 1000)
    old = seed.add_gift(db, None, date(2020, 1, 1), 5000)
    pending = seed.add_gift(db, None, date(2026, 11, 14), 500, attribution="pending_review")
    linked = seed.add_gift(db, donor, date(2026, 11, 14), 2000)
    db.commit()
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/app/auth/login",
            json={"email": "sam@example.org", "password": "correct horse battery"},
        ).status_code
        == 200
    )
    try:
        yield dict(
            client=client,
            owner=diana,
            actor=sam,
            donor=donor,
            gift=gift,
            old=old,
            pending=pending,
            linked=linked,
        )
    finally:
        set_clock(SystemClock())


def attribute(world, gift=None, donor=None):
    gift = world["gift"] if gift is None else gift
    donor = world["donor"] if donor is None else donor
    client = world["client"]
    return client.post(
        f"/api/app/gifts/{gift}/attribute",
        json={"donor_id": donor},
        headers={"X-CSRF-Token": client.cookies.get("cic_csrf")},
    )


def test_other_member_can_attribute_audit_and_timeline_without_changing_owner(world, db):
    actor = Actor(kind="user", id=world["actor"])
    period = dict(start=date(2020, 1, 1), end=date(2026, 11, 15))
    before = reports.totals(db, actor, **period)["gross_cents"]
    response = attribute(world)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["donor_id"] == world["donor"] and body["attribution"] == "linked"
    assert not body["assumed_thanked"]
    db.expire_all()
    assert db.get(Donor, world["donor"]).owner_user_id == world["owner"]
    assert db.get(User, world["owner"]).last_assigned_at is None
    assert list(db.scalars(select(OwnerHistory))) == []
    assert list(db.scalars(select(Interaction))) == []
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "gift.attribute"))
    assert audit.actor_id == world["actor"] and audit.entity_id == world["gift"]
    assert audit.data["donor_id"] == world["donor"]
    timeline = world["client"].get(f"/api/app/donors/{world['donor']}/timeline").json()["items"]
    assert any(item["kind"] == "gift" and item["entity_id"] == world["gift"] for item in timeline)
    unattributed = world["client"].get("/api/app/gifts/unattributed").json()["items"]
    assert world["gift"] not in {gift["id"] for gift in unattributed}
    assert reports.totals(db, actor, **period)["gross_cents"] == before


def test_old_gift_is_assumed_thanked_and_matching_gift_never_credits_employee(world, db):
    db.execute(
        text("UPDATE gifts SET is_matching_gift = true WHERE id = :id"), {"id": world["old"]}
    )
    db.commit()
    response = attribute(world, world["old"])
    assert response.status_code == 200
    assert response.json()["assumed_thanked"] and response.json()["is_matching_gift"]
    detail = world["client"].get(f"/api/app/donors/{world['donor']}").json()
    assert detail["total_lifetime_cents"] == 2000


@pytest.mark.parametrize("key", ["pending", "linked"])
def test_only_anonymous_gifts_can_be_attributed(world, key):
    assert attribute(world, world[key]).status_code == 409


def test_repeated_attribution_is_a_conflict_and_does_not_duplicate_audit(world, db):
    assert attribute(world).status_code == 200
    assert attribute(world).status_code == 409
    assert len(list(db.scalars(select(AuditLog).where(AuditLog.action == "gift.attribute")))) == 1


def test_unknown_or_deleted_gift_and_donor_are_404(world, db):
    assert attribute(world, gift=999999).status_code == 404
    assert attribute(world, donor=999999).status_code == 404
    db.get(Donor, world["donor"]).deleted_at = NOW
    db.commit()
    assert attribute(world).status_code == 404
    db.get(Gift, world["gift"]).deleted_at = NOW
    db.commit()
    assert attribute(world).status_code == 404


def test_attribute_needs_session_csrf_and_review_policy(world, monkeypatch):
    path = f"/api/app/gifts/{world['gift']}/attribute"
    body = {"donor_id": world["donor"]}
    assert TestClient(create_app()).post(path, json=body).status_code == 401
    assert world["client"].post(path, json=body).status_code == 403
    monkeypatch.setattr(policy, "can", lambda *args, **kwargs: False)
    assert attribute(world).status_code == 403


def test_attribution_uses_review_permission_rather_than_owner_or_import_permission(
    world, monkeypatch
):
    monkeypatch.setattr(
        policy, "can", lambda actor, action, resource=None: action == "review.decide"
    )
    assert attribute(world).status_code == 200
