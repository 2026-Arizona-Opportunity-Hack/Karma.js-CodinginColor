"""Run the actual importer, not the reference resolver, against the fixture manifest."""

import csv
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.authz import policy
from app.authz.actor import Actor
from app.clock import FixedClock, SystemClock, set_clock
from app.db.models import (
    AuditLog,
    Donor,
    Gift,
    ImportBatch,
    ImportRow,
    MatchReview,
    OwnerHistory,
)
from app.errors import Invalid
from app.main import create_app
from app.repos import reports
from app.services.reports import retention
from tests import seed

FIX = Path(__file__).resolve().parents[3] / "fixtures"
M = json.loads((FIX / "manifest.json").read_text())
NOW = datetime(2026, 11, 15, 16, tzinfo=UTC)


@pytest.fixture
def world(db):
    clock = FixedClock(NOW)
    set_clock(clock)
    users = [seed.add_user(db, name) for name in ("Diana", "Sam", "Dev")]
    inactive = seed.add_user(db, "Inactive", active=False)
    db.commit()
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/app/auth/login",
            json={"email": "diana@example.org", "password": "correct horse battery"},
        ).status_code
        == 200
    )
    try:
        yield dict(client=client, users=users, inactive=inactive, clock=clock)
    finally:
        set_clock(SystemClock())


def post(world, path, **kwargs):
    client = world["client"]
    return client.post(
        "/api/app" + path, headers={"X-CSRF-Token": client.cookies.get("cic_csrf")}, **kwargs
    )


def preview(world, data, source="generic", filename="gifts.csv"):
    response = post(
        world, "/imports/preview", data={"source": source}, files={"file": (filename, data)}
    )
    assert response.status_code == 200, response.text
    return response.json()


def commit(world, body):
    response = post(world, f"/imports/{body['batch']['id']}/commit")
    assert response.status_code == 200, response.text
    return response.json()


def generic(name="Ada Jones", email="ada@example.org", txn="G1", amount="10", when="2026-11-14"):
    return (
        f"Date,Amount,Platform,Donor name,Email,Transaction ID\n"
        f"{when},{amount},other,{name},{email},{txn}\n"
    ).encode()


def count(db, model, *where):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model).where(*where))


def shuffled_or_overlap(filename, overlap=False):
    rows = list(csv.reader(StringIO((FIX / filename).read_text(encoding="utf-8"))))
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(rows[0])
    writer.writerows(rows[1::2] if overlap else reversed(rows[1:]))
    return output.getvalue().encode()


def test_finished_importer_matches_manifest_and_acceptance_1_to_4(world, db):
    actor = Actor(kind="user", id=world["users"][0])
    sources = ["spreadsheet", "zeffy", "benevity", "generic"]
    for source, filename in zip(sources, M["import_order"], strict=True):
        expected = M["files"][filename]
        body = preview(world, (FIX / filename).read_bytes(), source, filename)
        saved = commit(world, body)
        assert saved["id"] == body["batch"]["id"] and saved["status"] == "committed"
        summary = saved["summary"]
        assert summary["rows_read"] == expected["rows"]
        assert summary["new_donors"] == expected["created_donors"]
        assert summary["gift_count"] == expected.get("valid_gifts", 0)
        assert summary["total_cents"] == expected.get("gross_cents", 0)
        assert summary["donation_cents"] == expected.get("donation_cents", 0)
        assert summary["match_cents"] == expected.get("match_cents", 0)
        assert summary["rows_reconcile"] and summary["cents_reconcile"] and summary["reconciles"]
        db.expire_all()
        batch = db.get(ImportBatch, saved["id"])
        assert batch.file_sha256 == expected["sha256"]
        if source == "benevity":
            assert sum(batch.summary["disbursements"].values()) == 80
        rows = list(
            db.scalars(
                select(ImportRow)
                .where(ImportRow.batch_id == batch.id)
                .order_by(ImportRow.row_number)
            )
        )
        assert [
            {"row": r.row_number, "code": r.reason} for r in rows if r.status == "invalid"
        ] == expected["invalid"]
        gifts = list(db.scalars(select(Gift).where(Gift.import_batch_id == batch.id)))
        assert len(gifts) == expected.get("valid_gifts", 0)
        for attr, value in expected.get("by_attribution", {}).items():
            items = [g for g in gifts if g.attribution == attr]
            assert len(items) == value["gifts"]
            assert sum(g.gross_cents for g in items) == value["cents"]
            assert sum(g.gross_cents for g in items if g.is_matching_gift) == value["match_cents"]
        assert all(g.net_cents == g.gross_cents - g.fee_cents for g in gifts)
        assert all(g.assumed_thanked == (g.gift_date < batch.cutoff_date) for g in gifts)
    assert count(db, Donor) == 225
    assert count(db, Gift) == 531
    assert count(db, MatchReview) == 19
    assert count(db, ImportRow, ImportRow.status == "invalid") == 14
    assert count(db, Gift, Gift.source == "benevity", Gift.attribution == "anonymous") == 13
    owners = Counter(db.scalars(select(Donor.owner_user_id)))
    assert owners == dict.fromkeys(world["users"], 75)
    assert count(db, OwnerHistory) == 225
    assert count(db, AuditLog, AuditLog.action == "import.commit") == 4
    result = retention.build(db, actor, as_of=date.fromisoformat(M["demo_now"]), basis="rolling")
    assert {k: v.model_dump() for k, v in result.classes.items()} == M["retention"]["classes"]
    reviews = world["client"].get("/api/app/reviews").json()["items"]
    reason = {
        "email_name_conflict": "name_conflict",
        "phone": "phone",
        "name_employer": "name_employer",
    }
    actual = [
        {
            "file": r["file"],
            "row": r["row_number"],
            "reason": (
                "household"
                if r["file"].endswith(".xlsx")
                else reason[r["candidates"][0]["match_reason"]]
            ),
        }
        for r in reviews
    ]
    assert actual == M["review_items"]
    org = reports.totals(db, actor, start=date(2020, 1, 1), end=date(2026, 11, 15))
    assert org["gross_cents"] == sum(
        f["by_attribution"][a]["cents"]
        for f in M["files"].values()
        if "by_attribution" in f
        for a in ("linked", "anonymous")
    )
    # Same files are blocked; shuffled and overlapping gift exports add nothing.
    for source, filename in zip(sources, M["import_order"], strict=True):
        assert (
            post(
                world,
                "/imports/preview",
                data={"source": source},
                files={"file": (filename, (FIX / filename).read_bytes())},
            ).status_code
            == 409
        )
        if source == "spreadsheet":
            continue
        for overlap in (False, True):
            body = preview(world, shuffled_or_overlap(filename, overlap), source, filename)
            assert body["summary"]["new_gifts"]["count"] == 0
            assert body["summary"]["new_donors"] == 0
            commit(world, body)
            assert count(db, Gift) == 531 and count(db, Donor) == 225
            assert count(db, MatchReview) == 19
    # Resolve a phone match; the next file learns the reviewed email and preserves ownership.
    review = next(r for r in reviews if r["candidates"][0]["match_reason"] == "phone")
    donor = review["candidates"][0]["donor_id"]
    old_owner = db.get(Donor, donor).owner_user_id
    response = post(
        world, f"/reviews/{review['id']}/decide", json={"decision": "link", "donor_id": donor}
    )
    assert response.status_code == 200, response.text
    incoming = review["incoming"]
    body = preview(world, generic(incoming["display_name"], incoming["email"], "learned-email"))
    assert body["summary"]["new_donors"] == 0 and body["summary"]["donors_matched"] == 1
    commit(world, body)
    db.expire_all()
    assert db.get(Donor, donor).owner_user_id == old_owner
    # After a manual imbalance, a genuinely new donor goes to the lightest member.
    moved = db.scalar(select(Donor).where(Donor.owner_user_id == world["users"][1]).limit(1))
    moved.owner_user_id = world["users"][0]
    db.commit()
    commit(world, preview(world, generic("Fresh Person", "fresh@example.org", "fresh")))
    fresh = db.scalar(select(Donor).where(Donor.email == "fresh@example.org"))
    assert fresh.owner_user_id == world["users"][1]


def test_import_routes_allow_members_and_deny_missing_session_csrf_or_policy(
    world, db, monkeypatch
):
    body = preview(world, generic())
    batch_id = body["batch"]["id"]
    client = world["client"]
    assert client.get("/api/app/imports").status_code == 200
    assert client.get(f"/api/app/imports/{batch_id}").json()["status"] == "previewed"
    commit(world, body)
    assert client.get(f"/api/app/imports/{batch_id}").json()["status"] == "committed"
    routes = [
        ("GET", "/imports"),
        ("GET", f"/imports/{batch_id}"),
        ("POST", f"/imports/{batch_id}/commit"),
        ("POST", f"/imports/{batch_id}/reverse"),
    ]
    for method, path in routes:
        assert TestClient(create_app()).request(method, "/api/app" + path).status_code == 401
        if method == "POST":
            assert client.post("/api/app" + path).status_code == 403
    assert post(world, f"/imports/{batch_id}/commit").status_code == 409
    assert post(world, f"/imports/{batch_id}/reverse").status_code == 200
    assert post(world, f"/imports/{batch_id}/reverse").status_code == 409
    monkeypatch.setattr(policy, "can", lambda *args, **kwargs: False)
    for method, path in routes:
        response = client.request(
            method, "/api/app" + path, headers={"X-CSRF-Token": client.cookies.get("cic_csrf")}
        )
        assert response.status_code == 403


def test_commit_failure_rolls_back_everything_and_can_be_retried(world, db, monkeypatch):
    from app.repos import imports

    body = preview(world, generic())
    original = imports.save_row

    def fail(*args, **kwargs):
        raise Invalid("Injected failure")

    monkeypatch.setattr(imports, "save_row", fail)
    assert post(world, f"/imports/{body['batch']['id']}/commit").status_code == 400
    for model in (Donor, Gift, ImportBatch, ImportRow, OwnerHistory):
        assert count(db, model) == 0
    assert count(db, AuditLog, AuditLog.action.in_(["import.commit", "donor.assign"])) == 0
    monkeypatch.setattr(imports, "save_row", original)
    commit(world, body)
    assert count(db, Gift) == 1


@pytest.mark.parametrize("same_file", [False, True])
def test_concurrent_commits_serialize_assignment_and_block_duplicate_files(world, db, same_file):
    first = preview(world, generic())
    second = preview(
        world, generic() if same_file else generic("Bea Smith", "bea@example.org", "G2")
    )
    cookies = dict(world["client"].cookies)

    def run(body):
        client = TestClient(create_app())
        client.cookies.update(cookies)
        return client.post(
            f"/api/app/imports/{body['batch']['id']}/commit",
            headers={"X-CSRF-Token": cookies["cic_csrf"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(run, [first, second]))
    assert statuses == ([200, 409] if same_file else [200, 200])
    expected = 1 if same_file else 2
    assert count(db, Gift) == count(db, Donor) == count(db, ImportBatch) == expected
    counts = Counter(db.scalars(select(Donor.owner_user_id)))
    assert (
        max(counts.get(user, 0) for user in world["users"])
        - min(counts.get(user, 0) for user in world["users"])
        <= 1
    )


def test_reverse_soft_deletes_and_allows_reimport_without_double_counting(world, db):
    data = generic()
    saved = commit(world, preview(world, data))
    assert post(world, f"/imports/{saved['id']}/reverse").status_code == 200
    assert count(db, Gift, Gift.deleted_at.is_(None)) == 0
    assert count(db, Donor, Donor.deleted_at.is_(None)) == 0
    assert count(db, AuditLog, AuditLog.action == "import.reverse") == 1
    commit(world, preview(world, data))
    assert count(db, Gift) == 2 and count(db, Gift, Gift.deleted_at.is_(None)) == 1
    assert count(db, Donor, Donor.deleted_at.is_(None)) == 1


def test_reverse_preserves_donors_with_other_gifts(world, db):
    first = commit(world, preview(world, generic()))
    commit(world, preview(world, generic(txn="G2")))
    assert post(world, f"/imports/{first['id']}/reverse").status_code == 200
    assert count(db, Donor, Donor.deleted_at.is_(None)) == 1
    assert count(db, Gift, Gift.deleted_at.is_(None)) == 1


@pytest.mark.parametrize("same_gift", [False, True])
def test_stale_preview_rechecks_gift_and_donor_identity_inside_commit(world, db, same_gift):
    first = preview(world, generic())
    second = preview(world, generic() + b"\n" if same_gift else generic(txn="G2"))
    assert second["summary"]["new_donors"] == 1
    commit(world, first)
    saved = commit(world, second)
    assert saved["summary"]["new_donors"] == 0
    assert count(db, Donor) == count(db, OwnerHistory) == 1
    assert count(db, Gift) == (1 if same_gift else 2)
    if same_gift:
        assert saved["summary"]["new_gifts"]["count"] == 0
        assert saved["summary"]["already_imported"]["count"] == 1


def test_round_robin_creation_order_is_first_gift_date_then_name(world, db):
    data = (
        b"Date,Amount,Platform,Donor name,Email\n"
        b"2026-11-14,10,other,Zed Jones,zed@example.org\n"
        b"2026-11-13,10,other,Bob Jones,bob@example.org\n"
        b"2026-11-13,10,other,Ada Jones,ada@example.org\n"
    )
    commit(world, preview(world, data))
    actual = {d.display_name: d.owner_user_id for d in db.scalars(select(Donor))}
    assert actual == dict(zip(["Ada Jones", "Bob Jones", "Zed Jones"], world["users"], strict=True))


def test_reverse_closes_open_reviews_without_remembering_an_anonymous_identity(world, db):
    data = b"Name,Email\nAda Jones,ada@example.org\nBea Jones,ada@example.org\n"
    saved = commit(world, preview(world, data, "spreadsheet", "donors.csv"))
    assert count(db, MatchReview, MatchReview.status == "open") == 1
    assert post(world, f"/imports/{saved['id']}/reverse").status_code == 200
    assert count(db, MatchReview, MatchReview.status == "open") == 0
    again = preview(world, data, "spreadsheet", "donors.csv")
    assert again["summary"]["new_donors"] == 1
    assert again["summary"]["needs_review"]["count"] == 1


def test_reverse_removes_a_donor_created_by_review_of_its_gift(world, db):
    commit(
        world,
        preview(world, b"Name,Email\nAda Jones,ada@example.org\n", "spreadsheet", "donors.csv"),
    )
    pending = commit(world, preview(world, generic("Bea Jones")))
    reviews = world["client"].get("/api/app/reviews").json()["items"]
    response = post(world, f"/reviews/{reviews[0]['id']}/decide", json={"decision": "create_new"})
    assert response.status_code == 200, response.text
    assert count(db, Donor, Donor.deleted_at.is_(None)) == 2
    assert post(world, f"/imports/{pending['id']}/reverse").status_code == 200
    assert count(db, Donor, Donor.deleted_at.is_(None)) == 1
    assert db.scalar(select(Donor.display_name).where(Donor.deleted_at.is_(None))) == "Ada Jones"


def test_commit_rejects_disabled_preview_and_expired_or_unknown_ids(world, db):
    from app.services.ingest.preview import previews

    body = preview(world, generic())
    state = previews.get(body["batch"]["id"], world["clock"])
    state.output.commit_allowed = False
    previews.put(state, world["clock"])
    assert post(world, f"/imports/{body['batch']['id']}/commit").status_code == 409
    assert count(db, ImportBatch) == 0
    assert post(world, "/imports/0/commit").status_code == 404
    assert post(world, "/imports/0/reverse").status_code == 404
    assert world["client"].get("/api/app/imports/0").status_code == 404
