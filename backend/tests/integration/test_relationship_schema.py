from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AppSetting,
    Donor,
    ImportBatch,
    ImportRow,
    Interaction,
    MatchReview,
    Message,
    NextStep,
    User,
)

NOW = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)


@pytest.fixture
def base(db: Session) -> tuple[User, Donor]:
    u = User(email="u@example.org", display_name="U", password_hash="x")
    d = Donor(kind="person", display_name="Ada", created_via="manual")
    db.add_all([u, d])
    db.flush()
    return u, d


def message(db: Session, d: Donor, **kw) -> Message:
    m = Message(
        **({"donor_id": d.id, "kind": "quarterly_update", "channel": "email", "body": "Hi"} | kw)
    )
    db.add(m)
    db.flush()
    return m


def test_settings_defaults_are_seeded(db: Session) -> None:
    rows = {r.key: r.value for r in db.execute(select(AppSetting)).scalars()}
    assert rows == {
        "thank_you_days_first": 2,
        "thank_you_days_repeat": 7,
        "quarterly_days": 90,
        "import_cutoff_days": 60,
        "retention_basis": "rolling",
    }


# --- messages: approval gate enforced by the database (MSG-3, MSG-4) ---


def test_draft_is_the_default_state(db: Session, base) -> None:
    assert message(db, base[1]).status == "draft"


def test_cannot_send_without_approval(db: Session, base) -> None:
    with pytest.raises(IntegrityError):
        message(db, base[1], status="sent", sent_at=NOW, sent_by=base[0].id)


def test_cannot_mark_manually_sent_without_approval(db: Session, base) -> None:
    with pytest.raises(IntegrityError):
        message(db, base[1], channel="sms", status="sent_manually", sent_at=NOW)


def test_cannot_approve_without_approver_and_body_hash(db: Session, base) -> None:
    with pytest.raises(IntegrityError):
        message(db, base[1], status="approved", approved_at=NOW)
    db.rollback()
    u = User(email="v@example.org", display_name="V", password_hash="x")
    d = Donor(kind="person", display_name="Bo", created_via="manual")
    db.add_all([u, d])
    db.flush()
    with pytest.raises(IntegrityError):  # approver but no body hash
        message(db, d, status="approved", approved_by=u.id, approved_at=NOW)


def test_full_happy_path_is_allowed(db: Session, base) -> None:
    u, d = base
    approved = dict(approved_by=u.id, approved_at=NOW, body_sha256_at_approval="abc")
    m = message(db, d, status="approved", **approved)
    m.status, m.sent_at, m.sent_by, m.delivery_mode = "sent", NOW, u.id, "dry_run"
    db.flush()


@pytest.mark.parametrize(
    "field,value",
    [("status", "queued"), ("kind", "spam"), ("channel", "fax"), ("delivery_mode", "yolo")],
)
def test_message_enums_are_checked(db: Session, base, field: str, value: str) -> None:
    with pytest.raises(IntegrityError):
        message(db, base[1], **{field: value})


def test_one_open_message_per_donor_and_kind(db: Session, base) -> None:
    u, d = base
    message(db, d)
    with pytest.raises(IntegrityError):
        message(db, d)  # second open quarterly update (MSG-2)
    db.rollback()
    u = User(email="w@example.org", display_name="W", password_hash="x")
    d = Donor(kind="person", display_name="Cy", created_via="manual")
    db.add_all([u, d])
    db.flush()
    first = message(db, d)
    first.status = "cancelled"
    db.flush()
    message(db, d)  # closing the old draft frees the slot
    message(db, d, kind="lapsed_nudge")  # other kinds are independent


def test_one_open_thank_you_per_gift_but_donor_may_have_many(db: Session, base) -> None:
    _, d = base
    batch_user = base[0]
    from app.db.models import Gift, Program

    general = db.execute(select(Program).where(Program.name == "General")).scalar_one()
    gifts = []
    for i in range(2):
        g = Gift(
            donor_id=d.id, attribution="linked", source="manual", row_key=f"k{i}",
            gift_date=date(2026, 10, 1), gross_cents=100, net_cents=100, program_id=general.id,
            created_by=batch_user.id,
        )  # fmt: skip
        db.add(g)
        gifts.append(g)
    db.flush()
    message(db, d, kind="thank_you", gift_id=gifts[0].id)
    message(db, d, kind="thank_you", gift_id=gifts[1].id)  # different gift: fine
    with pytest.raises(IntegrityError):
        message(db, d, kind="thank_you", gift_id=gifts[0].id)


# --- next steps, interactions ---


def test_one_open_next_step_per_donor(db: Session, base) -> None:
    u, d = base

    def step(status: str = "open", done_at=None) -> None:
        db.add(
            NextStep(
                donor_id=d.id, title="Call", due_date=date(2026, 12, 1), created_by=u.id,
                status=status, done_at=done_at,
            )
        )  # fmt: skip
        db.flush()

    step()
    with pytest.raises(IntegrityError):
        step()
    db.rollback()
    u = User(email="x@example.org", display_name="X", password_hash="x")
    d = Donor(kind="person", display_name="Di", created_via="manual")
    db.add_all([u, d])
    db.flush()
    step("done", NOW)  # finished steps do not count
    step("cancelled")
    step()


def test_done_step_needs_done_at_and_vice_versa(db: Session, base) -> None:
    u, d = base
    db.add(
        NextStep(
            donor_id=d.id, title="t", due_date=date(2026, 12, 1), created_by=u.id, status="done"
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_interaction_kind_is_checked_and_system_has_no_user(db: Session, base) -> None:
    _, d = base
    db.add(Interaction(donor_id=d.id, kind="system", occurred_on=date(2026, 11, 14)))
    db.flush()
    db.add(Interaction(donor_id=d.id, kind="gossip", occurred_on=date(2026, 11, 14)))
    with pytest.raises(IntegrityError):
        db.flush()


# --- import rows and reviews ---


def test_invalid_rows_must_say_why(db: Session, base) -> None:
    u, _ = base
    b = ImportBatch(source="zeffy", filename="f.csv", file_sha256="h", uploaded_by=u.id)
    db.add(b)
    db.flush()
    db.add(ImportRow(batch_id=b.id, row_number=1, status="invalid"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    u = User(email="y@example.org", display_name="Y", password_hash="x")
    db.add(u)
    db.flush()
    b = ImportBatch(source="zeffy", filename="f.csv", file_sha256="h", uploaded_by=u.id)
    db.add(b)
    db.flush()
    db.add(ImportRow(batch_id=b.id, row_number=1, status="invalid", reason="bad date"))
    db.flush()
    db.add(ImportRow(batch_id=b.id, row_number=1, status="new"))  # row numbers are unique
    with pytest.raises(IntegrityError):
        db.flush()


def test_review_is_open_until_decided_with_who_and_when(db: Session, base) -> None:
    u, _ = base
    db.add(MatchReview(incoming={"email": "a@b.c"}))
    db.flush()  # defaults: open, no candidates
    db.add(MatchReview(incoming={}, status="linked"))  # decided but nobody recorded
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    u = User(email="z@example.org", display_name="Z", password_hash="x")
    db.add(u)
    db.flush()
    db.add(MatchReview(incoming={}, status="linked", decided_by=u.id, decided_at=NOW))
    db.flush()
    db.add(MatchReview(incoming={}, status="open", decided_by=u.id, decided_at=NOW))
    with pytest.raises(IntegrityError):
        db.flush()


def test_review_candidates_default_to_empty_array(db: Session) -> None:
    r = MatchReview(incoming={})
    db.add(r)
    db.flush()
    assert db.execute(text("SELECT candidate_donor_ids FROM match_reviews")).scalar() == []
