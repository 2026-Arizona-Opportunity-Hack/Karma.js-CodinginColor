"""The approval state machine (MSG-3, MSG-4): who may move a message and which moves exist."""

# ruff: noqa: F811 (the fixtures come from tests.msgkit and are used as arguments)
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.main import create_app
from tests.msgkit import clock, draft, login, make_super_admin, patch, post, row, w  # noqa: F401

DIANA = "diana.owner@example.org"
SAM = "sam.other@example.org"


def test_approve_records_who_when_and_a_hash(db: Session, w) -> None:
    c = login(DIANA)
    m = draft(c, w)
    r = post(c, f"/messages/{m['id']}/approve")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "approved" and out["approved_by"]["display_name"] == "Diana Owner"
    assert out["approved_at"].startswith("2026-11-15T16:00")
    stored = row(db, m["id"])
    assert stored["status"] == "approved" and len(stored["body_sha256_at_approval"]) == 64
    assert stored["sent_at"] is None  # approving is not sending


def test_editing_an_approved_message_returns_it_to_draft_and_clears_approval(
    db: Session, w
) -> None:
    c = login(DIANA)
    m = draft(c, w)
    post(c, f"/messages/{m['id']}/approve")
    r = patch(c, f"/messages/{m['id']}", {"body": "Changed words"})
    assert r.status_code == 200 and r.json()["status"] == "draft"
    assert r.json()["approved_by"] is None and r.json()["approved_at"] is None
    stored = row(db, m["id"])
    assert stored["body_sha256_at_approval"] is None and stored["approved_by"] is None
    assert post(c, f"/messages/{m['id']}/approve").json()["status"] == "approved"  # a new click


def test_the_hash_covers_the_subject_as_well_as_the_body(db: Session, w) -> None:
    c = login(DIANA)
    a = draft(c, w, text_body="Same words")
    post(c, f"/messages/{a['id']}/approve")
    first = row(db, a["id"])["body_sha256_at_approval"]
    patch(c, f"/messages/{a['id']}", {"subject": "A new subject"})
    post(c, f"/messages/{a['id']}/approve")
    assert row(db, a["id"])["body_sha256_at_approval"] != first


def test_a_second_approval_and_other_bad_moves_are_409(db: Session, w) -> None:
    c = login(DIANA)
    m = draft(c, w)
    assert post(c, f"/messages/{m['id']}/approve").status_code == 200
    assert post(c, f"/messages/{m['id']}/approve").status_code == 409  # already approved
    assert post(c, f"/messages/{m['id']}/cancel").status_code == 200
    for r in (
        post(c, f"/messages/{m['id']}/approve"),
        post(c, f"/messages/{m['id']}/cancel"),
        patch(c, f"/messages/{m['id']}", {"body": "x"}),
    ):
        assert r.status_code == 409 and r.json()["error"]["code"] == "conflict", r.text
    assert row(db, m["id"])["status"] == "cancelled"


@pytest.mark.parametrize("status", ["sent", "sent_manually", "failed"])
def test_finished_messages_cannot_be_edited_approved_or_cancelled(db: Session, w, status) -> None:
    c = login(DIANA)
    m = draft(c, w)
    db.execute(
        text(
            "UPDATE messages SET status = :s, approved_by = created_by, approved_at = now(), "
            "body_sha256_at_approval = 'h', sent_at = now() WHERE id = :i"
        ),
        {"s": status, "i": m["id"]},
    )
    db.commit()
    for r in (
        patch(c, f"/messages/{m['id']}", {"body": "x"}),
        post(c, f"/messages/{m['id']}/approve"),
        post(c, f"/messages/{m['id']}/cancel"),
    ):
        assert r.status_code == 409
    assert row(db, m["id"])["status"] == status


def test_cancelling_a_draft_frees_the_gift_for_a_new_draft(w) -> None:
    c = login(DIANA)
    m = draft(c, w)
    assert post(c, f"/messages/{m['id']}/cancel").json()["status"] == "cancelled"
    body = {"kind": "thank_you", "channel": "email", "gift_id": w["gift"]}
    again = post(c, f"/donors/{w['zelda']}/messages", body)
    assert again.status_code == 201 and again.json()["id"] != m["id"]


def test_a_draft_with_edit_markers_cannot_be_approved(w) -> None:
    c = login(DIANA)
    body = {"kind": "quarterly_update", "channel": "email"}
    q = post(c, f"/donors/{w['zelda']}/messages", body).json()
    r = post(c, f"/messages/{q['id']}/approve")
    assert r.status_code == 400 and "[EDIT" in r.json()["error"]["message"]
    fixed = patch(c, f"/messages/{q['id']}", {"body": "Hi Zelda, thank you for a great quarter."})
    assert fixed.status_code == 200
    assert post(c, f"/messages/{q['id']}/approve").status_code == 200


def test_cannot_approve_after_do_not_contact_or_with_no_address(db: Session, w) -> None:
    c = login(DIANA)
    m = draft(c, w)
    db.execute(text("UPDATE donors SET do_not_contact = true WHERE id = :d"), {"d": w["zelda"]})
    db.commit()
    assert post(c, f"/messages/{m['id']}/approve").status_code == 409
    db.execute(
        text("UPDATE donors SET do_not_contact = false, email = NULL WHERE id = :d"),
        {"d": w["zelda"]},
    )
    db.commit()
    r = post(c, f"/messages/{m['id']}/approve")
    assert r.status_code == 400 and "email" in r.json()["error"]["message"]
    assert row(db, m["id"])["status"] == "draft"


def test_empty_edit_is_400(w) -> None:
    c = login(DIANA)
    m = draft(c, w)
    assert patch(c, f"/messages/{m['id']}", {}).status_code == 400
    assert patch(c, f"/messages/{m['id']}", {"body": ""}).status_code == 400


def test_sms_edit_ignores_a_subject(w) -> None:
    c = login(DIANA)
    m = draft(c, w, channel="sms")
    out = patch(c, f"/messages/{m['id']}", {"subject": "nope", "body": "Hi"}).json()
    assert out["subject"] is None and out["body"] == "Hi"


# --- who may move a message ---------------------------------------------------------------------
def test_a_non_owner_gets_403_on_every_move_and_nothing_changes(db: Session, w) -> None:
    m = draft(login(DIANA), w)
    sam = login(SAM)
    for r in (
        patch(sam, f"/messages/{m['id']}", {"body": "hijack"}),
        post(sam, f"/messages/{m['id']}/approve"),
        post(sam, f"/messages/{m['id']}/cancel"),
    ):
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    stored = row(db, m["id"])
    assert stored["status"] == "draft" and stored["body"] == "Hello Zelda"


def test_unknown_message_is_404(w) -> None:
    c = login(DIANA)
    assert post(c, "/messages/999999/approve").status_code == 404
    assert patch(c, "/messages/999999", {"body": "x"}).status_code == 404
    assert post(c, "/messages/999999/cancel").status_code == 404


def test_active_super_admin_may_approve_for_another_owner_a_dormant_one_may_not(
    db: Session, w
) -> None:
    m = draft(login(DIANA), w)
    make_super_admin(db, w["sam"])
    sam = login(SAM)
    out = post(sam, f"/messages/{m['id']}/approve").json()
    assert out["approved_by"]["display_name"] == "Sam Other"
    make_super_admin(db, w["sam"], "dormant")
    assert post(sam, f"/messages/{m['id']}/cancel").status_code == 403


def test_logged_out_is_401_and_missing_csrf_is_403(w) -> None:
    m = draft(login(DIANA), w)
    assert TestClient(create_app()).post(f"/api/app/messages/{m['id']}/approve").status_code == 401
    assert login(DIANA).post(f"/api/app/messages/{m['id']}/approve").status_code == 403


def test_every_move_is_audited_without_the_words(db: Session, w) -> None:
    c = login(DIANA)
    m = draft(c, w, text_body="PRIVATE WORDS")
    post(c, f"/messages/{m['id']}/approve")
    patch(c, f"/messages/{m['id']}", {"body": "PRIVATE EDIT"})
    post(c, f"/messages/{m['id']}/cancel")
    rows = db.execute(
        text("SELECT action, data::text FROM audit_log WHERE entity = 'message' ORDER BY id")
    ).all()
    assert [a for a, _ in rows if a != "message.draft"] == [
        "message.edit", "message.approve", "message.edit", "message.cancel",
    ]  # fmt: skip
    assert not any("PRIVATE" in d or "Zelda" in d for _, d in rows)


# --- the database says no, even if the code were wrong ----------------------------------------
def test_the_database_refuses_sent_or_approved_without_an_approval(db: Session, w) -> None:
    m = draft(login(DIANA), w)
    for sql in (
        "UPDATE messages SET status = 'sent', sent_at = now() WHERE id = :i",  # never approved
        "UPDATE messages SET status = 'approved' WHERE id = :i",  # no approver or hash
        "UPDATE messages SET status = 'sent_manually', sent_at = now() WHERE id = :i",
    ):
        with pytest.raises(IntegrityError):
            db.execute(text(sql), {"i": m["id"]})
            db.flush()
        db.rollback()
