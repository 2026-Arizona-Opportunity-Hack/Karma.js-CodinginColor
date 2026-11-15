"""Uploader-approved fields are the only changes permitted to existing spreadsheet donors."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db.models import AuditLog, Donor, DonorIdentity, ImportBatch, OwnerHistory
from app.main import create_app
from tests import seed
from tests.integration import test_import_commit as import_support

world = import_support.world
post = import_support.post
preview = import_support.preview

DATA = (
    b"Name,Contact ID,Organization,Email,Phone,Notes\n"
    b"Ada M Jones,C1,New Org,new@example.org,+16025550102,New notes\n"
)


@pytest.fixture
def donor(db, world):
    identifier = seed.add_donor(
        db,
        "Ada Jones",
        owner=world["users"][0],
        email="old@example.org",
        phone="+16025550101",
        notes="Old notes",
    )
    db.get(Donor, identifier).organization = "Old Org"
    db.add(
        DonorIdentity(donor_id=identifier, kind="zeffy_contact", value_norm="C1", source="zeffy")
    )
    db.commit()
    return identifier


def upload(world):
    return preview(world, DATA, "spreadsheet", "updates.csv")


def approve(world, body, donor, fields):
    return post(
        world,
        f"/imports/{body['batch']['id']}/commit",
        json={
            "approved_updates": [{"donor_id": donor, "fields": fields}],
        },
    )


def test_preview_lists_updates_and_commit_applies_only_selected_fields(world, donor, db):
    body = upload(world)
    assert body["summary"]["updated_count"] == body["summary"]["donor_updates"]["count"] == 1
    assert body["summary"]["already_imported"]["count"] == 0
    assert body["summary"]["reconciles"]
    update = body["updates"][0]
    assert update["donor_id"] == donor and update["donor_name"] == "Ada Jones"
    assert update["changes"]["email"]["old_value"] == "old@example.org"
    assert update["changes"]["email"]["new_value"] == "new@example.org"
    response = approve(world, body, donor, ["name", "email"])
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["updated_count"] == 1
    assert response.json()["summary"]["reconciles"]
    db.expire_all()
    record = db.get(Donor, donor)
    assert (record.display_name, record.email) == ("Ada M Jones", "new@example.org")
    assert (record.organization, record.phone, record.notes) == (
        "Old Org",
        "+16025550101",
        "Old notes",
    )
    assert record.owner_user_id == world["users"][0]
    assert db.scalar(select(func.count()).select_from(OwnerHistory)) == 0
    assert (
        db.scalar(select(DonorIdentity.id).where(DonorIdentity.value_norm == "+16025550102"))
        is None
    )
    audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "donor.import_update")))
    assert len(audits) == 1 and audits[0].entity_id == donor
    assert audits[0].data["fields"] == ["email", "name"]
    assert "old@example.org" not in json.dumps(audits[0].data)


def test_omitted_approvals_leave_every_existing_field_unchanged(world, donor, db):
    body = upload(world)
    response = post(world, f"/imports/{body['batch']['id']}/commit")
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["updated_count"] == 0
    assert response.json()["summary"]["reconciles"]
    db.expire_all()
    record = db.get(Donor, donor)
    assert (record.display_name, record.email, record.phone, record.notes) == (
        "Ada Jones",
        "old@example.org",
        "+16025550101",
        "Old notes",
    )
    assert (
        db.scalar(select(DonorIdentity.id).where(DonorIdentity.value_norm == "new@example.org"))
        is None
    )
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "donor.import_update")) is None


def login_as_sam(world):
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/app/auth/login",
            json={"email": "sam@example.org", "password": "correct horse battery"},
        ).status_code
        == 200
    )
    world["client"] = client


def test_non_owner_cannot_see_old_contact_values(world, donor):
    login_as_sam(world)
    body = upload(world)
    for field in ("email", "phone"):
        change = body["updates"][0]["changes"][field]
        assert change["old_hidden"] and "old_value" not in change
    assert "old@example.org" not in json.dumps(body)
    assert "+16025550101" not in json.dumps(body)


def test_active_super_admin_can_see_old_values(world, donor, db):
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :id, super_admin_state = 'active'"),
        {"id": world["users"][1]},
    )
    db.commit()
    login_as_sam(world)
    assert upload(world)["updates"][0]["changes"]["email"]["old_value"] == "old@example.org"


def test_stale_approved_field_conflicts_atomically(world, donor, db):
    body = upload(world)
    db.get(Donor, donor).notes = "Concurrent notes"
    db.commit()
    response = approve(world, body, donor, ["email", "notes"])
    assert response.status_code == 409
    db.expire_all()
    assert db.get(Donor, donor).email == "old@example.org"
    assert db.scalar(select(func.count()).select_from(ImportBatch)) == 0


def test_unselected_concurrent_changes_are_preserved(world, donor, db):
    body = upload(world)
    db.get(Donor, donor).notes = "Concurrent notes"
    db.commit()
    assert approve(world, body, donor, ["email"]).status_code == 200
    db.expire_all()
    assert db.get(Donor, donor).notes == "Concurrent notes"


def test_approval_must_belong_to_uploader_and_offer_only_previewed_fields(world, donor):
    body = upload(world)
    login_as_sam(world)
    assert approve(world, body, donor, ["email"]).status_code == 403
    assert approve(world, body, donor, ["owner_user_id"]).status_code == 400


def test_name_alone_does_not_propose_an_existing_donor_update(world, donor):
    body = preview(world, b"Name,Notes\nAda Jones,New notes\n", "spreadsheet", "names.csv")
    assert body["updates"] == [] and body["summary"]["new_donors"] == 1


def test_duplicate_rows_reconcile_and_audit_once_per_donor(world, donor, db):
    body = preview(world, DATA + DATA.splitlines(keepends=True)[1], "spreadsheet", "twice.csv")
    assert body["summary"]["rows_read"] == body["summary"]["donor_updates"]["count"] == 2
    assert body["summary"]["updated_count"] == len(body["updates"]) == 1
    assert body["summary"]["reconciles"]
    assert approve(world, body, donor, ["email", "notes"]).status_code == 200
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "donor.import_update")
        )
        == 1
    )


def test_absent_columns_are_preserved_but_approved_empty_cell_clears(world, donor, db):
    body = preview(world, b"Name,Contact ID,Email\nAda Jones,C1,\n", "spreadsheet", "clear.csv")
    assert set(body["updates"][0]["changes"]) == {"email"}
    assert body["updates"][0]["changes"]["email"]["new_value"] == ""
    assert approve(world, body, donor, ["email"]).status_code == 200
    db.expire_all()
    record = db.get(Donor, donor)
    assert record.email is None
    assert record.phone == "+16025550101" and record.notes == "Old notes"


def test_non_owner_uploader_can_approve_without_changing_owner(world, donor, db):
    login_as_sam(world)
    body = upload(world)
    assert approve(world, body, donor, ["email"]).status_code == 200
    db.expire_all()
    assert db.get(Donor, donor).email == "new@example.org"
    assert db.get(Donor, donor).owner_user_id == world["users"][0]


def test_unoffered_field_and_duplicate_approvals_are_rejected(world, donor):
    body = preview(world, b"Name,Contact ID,Notes\nAda Jones,C1,New\n", "spreadsheet", "note.csv")
    assert approve(world, body, donor, ["email"]).status_code == 400
    response = post(
        world,
        f"/imports/{body['batch']['id']}/commit",
        json={
            "approved_updates": [
                {"donor_id": donor, "fields": ["notes"]},
                {"donor_id": donor, "fields": ["notes"]},
            ]
        },
    )
    assert response.status_code == 400


def test_already_applied_approval_is_noop_without_audit(world, donor, db):
    body = upload(world)
    db.get(Donor, donor).notes = "New notes"
    db.commit()
    response = approve(world, body, donor, ["notes"])
    assert response.status_code == 200 and response.json()["summary"]["updated_count"] == 0
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "donor.import_update")) is None
