"""Preview endpoint authorization, upload errors and read-only database behavior."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.authz import policy
from app.clock import FixedClock, SystemClock, set_clock
from app.db.models import Donor, Gift, ImportBatch, ImportRow, MatchReview
from app.main import create_app
from tests import seed

DATA = b"Date,Amount,Platform,Donor name,Email\n2026-11-14,10,other,Ada Jones,ada@example.org\n"
NOW = datetime(2026, 11, 15, 2, tzinfo=UTC)


@pytest.fixture
def member(db) -> Iterator[TestClient]:
    set_clock(FixedClock(NOW))
    seed.add_user(db, "Diana")
    db.commit()
    client = TestClient(create_app())
    response = client.post(
        "/api/app/auth/login",
        json={
            "email": "diana@example.org",
            "password": "correct horse battery",
        },
    )
    assert response.status_code == 200
    yield client
    set_clock(SystemClock())


def upload(client, data=DATA, filename="gifts.csv", csrf=True):
    headers = {"X-CSRF-Token": client.cookies.get("cic_csrf")} if csrf else {}
    return client.post(
        "/api/app/imports/preview",
        data={"source": "generic"},
        files={"file": (filename, data)},
        headers=headers,
    )


def test_preview_allowed_and_writes_no_import_donor_or_gift_rows(member, db):
    response = upload(member)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["new_donors"] == 1
    assert body["summary"]["new_gifts"] == {
        "count": 1,
        "cents": 1000,
        "gift_count": 1,
        "donation_cents": 1000,
        "match_cents": 0,
    }
    assert body["summary"]["rows_reconcile"] and body["summary"]["cents_reconcile"]
    assert body["commit_allowed"]
    assert body["batch"]["cutoff_date"] == "2026-09-15"
    for model in (ImportBatch, ImportRow, Donor, Gift, MatchReview):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_preview_matches_existing_donor_and_uses_program_mapping(member, db):
    from app.db.models import Program, SourceProgramMap
    from app.services.ingest.preview import previews

    donor = seed.add_donor(db, "Ada Jones", owner=1, email="ada@example.org")
    program = db.scalar(select(Program.id).where(Program.slug == "summer-camp"))
    db.add(SourceProgramMap(source="generic", source_value_norm="camp", program_id=program))
    db.commit()
    response = upload(
        member,
        DATA.replace(b"Email\n", b"Email,Campaign\n").replace(
            b"ada@example.org\n", b"ada@example.org,Camp\n"
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["new_donors"] == 0
    assert body["summary"]["donors_matched"] == 1
    state = previews.get(body["batch"]["id"], FixedClock(NOW))
    assert state.rows[0].donor_token == donor
    assert state.rows[0].gifts[0].program_id == program


def test_preview_requires_session_and_csrf(member):
    assert upload(TestClient(create_app()), csrf=False).status_code == 401
    assert upload(member, csrf=False).status_code == 403


def test_preview_policy_denial(member, monkeypatch):
    monkeypatch.setattr(policy, "can", lambda *args, **kwargs: False)
    assert upload(member).status_code == 403


@pytest.mark.parametrize(
    "data,filename,status",
    [
        (b"%PDF-1.7", "gifts.csv", 415),
        (DATA, "gifts.pdf", 415),
        (b"x" * (5 * 1024 * 1024 + 1), "gifts.csv", 413),
        (b"Date,Platform\n2026-11-14,other\n", "gifts.csv", 400),
    ],
)
def test_upload_errors(member, data, filename, status):
    assert upload(member, data, filename).status_code == status


def test_same_committed_file_returns_409_with_date_and_uploader(member, db):
    from hashlib import sha256

    db.add(
        ImportBatch(
            source="generic",
            filename="gifts.csv",
            file_sha256=sha256(DATA).hexdigest(),
            uploaded_by=1,
            status="committed",
            committed_at=NOW,
        )
    )
    db.commit()
    response = upload(member)
    assert response.status_code == 409
    assert "Diana" in response.text and "2026-11-14" in response.text
