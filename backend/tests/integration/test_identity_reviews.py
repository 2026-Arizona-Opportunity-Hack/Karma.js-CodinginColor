"""Review decisions update all gifts in a source row, learn identity, and audit atomically."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.authz import policy
from app.authz.actor import Actor
from app.clock import FixedClock, SystemClock, set_clock
from app.db.models import AuditLog, Donor, DonorIdentity, Gift, ImportBatch, ImportRow, MatchReview
from app.main import create_app
from app.repos import imports
from app.services.dedupe.resolver import IdentityIndex
from app.services.ingest.adapters import IncomingDonor
from tests import seed

NOW = datetime(2026, 11, 15, 16, tzinfo=UTC)


@pytest.fixture
def world(db):
    set_clock(FixedClock(NOW))
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    donor = seed.add_donor(
        db, "Ada Jones", owner=diana, email="ada@example.org", phone="+16025550100"
    )
    incoming = IncomingDonor(
        display_name="Ada Jones",
        first_name="Ada",
        last_name="Jones",
        email="work@example.org",
        phone="+16025550100",
    )
    batch = ImportBatch(
        source="benevity",
        filename="gifts.csv",
        file_sha256="review-file",
        uploaded_by=diana,
        status="committed",
        committed_at=NOW,
    )
    db.add(batch)
    db.flush()
    gift_ids = [
        seed.add_gift(
            db, None, date(2026, 11, 1), amount, attribution="pending_review", source="benevity"
        )
        for amount in (10000, 5000)
    ]
    db.execute(
        text("UPDATE gifts SET import_batch_id = :b WHERE id = ANY(:ids)"),
        {"b": batch.id, "ids": gift_ids},
    )
    db.execute(text("UPDATE gifts SET is_matching_gift = true WHERE id = :id"), {"id": gift_ids[1]})
    row = ImportRow(
        batch_id=batch.id, row_number=1, status="needs_review", reason="phone", gift_id=gift_ids[0]
    )
    db.add(row)
    db.flush()
    review = MatchReview(
        import_row_id=row.id,
        gift_id=gift_ids[0],
        incoming=incoming.model_dump() | {"_gift_ids": gift_ids},
        candidate_donor_ids=[donor],
    )
    db.add(review)
    db.commit()
    client = TestClient(create_app())
    login = client.post(
        "/api/app/auth/login",
        json={"email": "diana@example.org", "password": "correct horse battery"},
    )
    assert login.status_code == 200
    try:
        yield dict(
            client=client,
            diana=diana,
            sam=sam,
            donor=donor,
            incoming=incoming,
            review=review.id,
            gifts=gift_ids,
            batch=batch.id,
        )
    finally:
        set_clock(SystemClock())


def decide(world, decision="link", donor_id=None, **kwargs):
    client = world["client"]
    body = {"decision": decision}
    if donor_id is not None:
        body["donor_id"] = donor_id
    return client.post(
        f"/api/app/reviews/{world['review']}/decide",
        json=body,
        headers={"X-CSRF-Token": client.cookies.get("cic_csrf")},
        **kwargs,
    )


def resolve_again(db, world):
    current = imports.snapshot(db, Actor(kind="user", id=world["diana"]), "generic", b"new file")
    return IdentityIndex(current.donors, current.identities, current.remembered).resolve(
        world["incoming"]
    )


def test_review_list_shows_candidates_file_row_and_no_internal_metadata(world):
    response = world["client"].get("/api/app/reviews")
    assert response.status_code == 200
    review = response.json()["items"][0]
    assert review["file"] == "gifts.csv" and review["row_number"] == 1
    assert review["candidates"][0]["match_reason"] == "phone"
    assert review["candidates"][0]["display_name"] == "Ada Jones"
    assert "_gift_ids" not in review["incoming"]
    assert "email" not in review["candidates"][0]


def test_link_updates_donation_and_match_remembers_email_and_audits(world, db):
    response = decide(world, donor_id=world["donor"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "linked"
    db.expire_all()
    gifts = list(db.scalars(select(Gift).where(Gift.id.in_(world["gifts"]))))
    assert all(g.attribution == "linked" and g.donor_id == world["donor"] for g in gifts)
    assert db.get(Donor, world["donor"]).owner_user_id == world["diana"]
    identity = db.scalar(
        select(DonorIdentity).where(DonorIdentity.value_norm == "work@example.org")
    )
    assert identity.donor_id == world["donor"]
    assert resolve_again(db, world).donor_id == world["donor"]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "review.decide"))
    assert audit.actor_id == world["diana"] and audit.data["decision"] == "link"
    assert world["client"].get("/api/app/reviews").json()["items"] == []
    assert len(world["client"].get("/api/app/reviews?status=decided").json()["items"]) == 1
    assert decide(world, donor_id=world["donor"]).status_code == 409


def test_create_new_assigns_lightest_member_and_remembers_household_conflict(world, db):
    incoming = world["incoming"].model_copy(
        update={"email": "ada@example.org", "display_name": "Bea Jones", "first_name": "Bea"}
    )
    review = db.get(MatchReview, world["review"])
    review.incoming = incoming.model_dump() | {"_gift_ids": world["gifts"]}
    db.commit()
    world["incoming"] = incoming
    response = decide(world, "create_new")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "created_new"
    db.expire_all()
    gift = db.get(Gift, world["gifts"][0])
    assert gift.donor_id != world["donor"]
    created = db.get(Donor, gift.donor_id)
    assert created.owner_user_id == world["sam"]
    assert resolve_again(db, world).donor_id == created.id
    assert (
        db.scalar(
            select(DonorIdentity).where(
                DonorIdentity.kind == "email", DonorIdentity.value_norm == "ada@example.org"
            )
        ).donor_id
        == world["donor"]
    )


def test_anonymous_decision_updates_all_gifts_and_is_remembered(world, db):
    response = decide(world, "anonymous")
    assert response.status_code == 200, response.text
    db.expire_all()
    gifts = list(db.scalars(select(Gift).where(Gift.id.in_(world["gifts"]))))
    assert all(g.attribution == "anonymous" and g.donor_id is None for g in gifts)
    assert resolve_again(db, world).verdict == "anonymous"
    client = world["client"]
    response = client.post(
        "/api/app/imports/preview",
        data={"source": "generic"},
        files={
            "file": (
                "next.csv",
                b"Date,Amount,Platform,Donor name,Email,Phone\n"
                b"2026-11-14,10,other,Ada Jones,work@example.org,+16025550100\n",
            )
        },
        headers={"X-CSRF-Token": client.cookies.get("cic_csrf")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["anonymous"]["count"] == 1
    assert response.json()["summary"]["new_donors"] == 0


def test_old_gifts_stay_assumed_thanked_when_review_is_resolved(world, db):
    db.execute(
        text("UPDATE gifts SET gift_date = '2020-01-01' WHERE id = ANY(:ids)"),
        {"ids": world["gifts"]},
    )
    db.commit()
    assert decide(world, donor_id=world["donor"]).status_code == 200
    db.expire_all()
    assert all(db.get(Gift, gift).assumed_thanked for gift in world["gifts"])


def test_review_routes_require_session_csrf_and_policy(world, monkeypatch):
    client = TestClient(create_app())
    assert client.get("/api/app/reviews").status_code == 401
    assert (
        client.post(
            f"/api/app/reviews/{world['review']}/decide", json={"decision": "anonymous"}
        ).status_code
        == 401
    )
    assert (
        world["client"]
        .post(f"/api/app/reviews/{world['review']}/decide", json={"decision": "anonymous"})
        .status_code
        == 403
    )
    monkeypatch.setattr(policy, "can", lambda *args, **kwargs: False)
    assert world["client"].get("/api/app/reviews").status_code == 403
    assert decide(world, "anonymous").status_code == 403


def test_unknown_or_deleted_target_and_reversed_batch_are_rejected(world, db):
    assert decide(world, donor_id=999999).status_code == 404
    db.execute(text("UPDATE donors SET deleted_at = now() WHERE id = :id"), {"id": world["donor"]})
    db.commit()
    assert decide(world, donor_id=world["donor"]).status_code == 404
    db.execute(
        text("UPDATE import_batches SET status = 'reversed' WHERE id = :id"), {"id": world["batch"]}
    )
    db.commit()
    assert decide(world, "anonymous").status_code == 409


def test_review_decision_checks_its_own_policy_action(world, monkeypatch):
    monkeypatch.setattr(
        policy, "can", lambda actor, action, resource=None: action == "review.decide"
    )
    assert decide(world, "create_new").status_code == 200


def test_create_new_skips_inactive_members_and_records_owner_history(world, db):
    from app.db.models import OwnerHistory, User

    db.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": world["sam"]})
    db.commit()
    assert decide(world, "create_new").status_code == 200
    db.expire_all()
    gift = db.get(Gift, world["gifts"][0])
    donor = db.get(Donor, gift.donor_id)
    assert donor.owner_user_id == world["diana"]
    history = db.scalar(select(OwnerHistory).where(OwnerHistory.donor_id == donor.id))
    assert history.method == "round_robin" and history.changed_by == world["diana"]
    assert db.get(User, world["diana"]).last_assigned_at == NOW


def test_pending_revenue_is_excluded_until_resolved_and_employee_credit_excludes_match(world, db):
    from app.repos import donors, reports

    actor = Actor(kind="user", id=world["diana"])
    period = dict(start=date(2026, 1, 1), end=date(2026, 11, 15))
    assert reports.totals(db, actor, **period)["gross_cents"] == 0
    assert decide(world, donor_id=world["donor"]).status_code == 200
    assert reports.totals(db, actor, **period)["gross_cents"] == 15000
    card = donors.get_card(db, actor, world["donor"], today=date(2026, 11, 15))
    assert card["total_lifetime_cents"] == 10000


def test_learning_reclaims_platform_identity_from_a_soft_deleted_donor(world, db):
    db.add(
        DonorIdentity(
            donor_id=world["donor"], kind="zeffy_contact", value_norm="C1", source="zeffy"
        )
    )
    db.get(Donor, world["donor"]).deleted_at = NOW
    incoming = world["incoming"].model_copy(update={"zeffy_contact": "C1"})
    db.get(MatchReview, world["review"]).incoming = incoming.model_dump() | {
        "_gift_ids": world["gifts"]
    }
    db.commit()
    world["incoming"] = incoming
    assert decide(world, "create_new").status_code == 200
    db.expire_all()
    identity = db.scalar(select(DonorIdentity).where(DonorIdentity.kind == "zeffy_contact"))
    assert identity.donor_id != world["donor"]
    assert resolve_again(db, world).donor_id == identity.donor_id


def test_failed_create_decision_rolls_back_donor_assignment_and_audit(world, db):
    from sqlalchemy import func

    from app.db.models import OwnerHistory

    db.get(ImportBatch, world["batch"]).status = "reversed"
    db.commit()
    before = db.scalar(select(func.count()).select_from(Donor))
    assert decide(world, "create_new").status_code == 409
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Donor)) == before
    assert db.scalar(select(func.count()).select_from(OwnerHistory)) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action.in_(["review.decide", "donor.assign"]))
        )
        == 0
    )
    assert db.get(MatchReview, world["review"]).status == "open"
