"""Templates and drafts (MSG-1, MSG-2, MSG-8, D-127): merge fields, idempotent drafts,
do-not-contact, matching gifts, and who may do what."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from app.repos import messages as repo
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)
PW = "correct horse battery"


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    diana, sam = seed.add_user(db, "Diana Owner"), seed.add_user(db, "Sam Other")
    zelda = seed.add_donor(
        db, "Zelda Quill", owner=diana, email="zelda@pii.test", phone="+15550100"
    )
    gift = seed.add_gift(db, zelda, date(2026, 11, 3), 5000, program="AI Academy")
    match = seed.add_gift(db, zelda, date(2026, 11, 3), 5000)
    db.execute(text("UPDATE gifts SET is_matching_gift = true WHERE id = :g"), {"g": match})
    nia = seed.add_donor(db, "Nia Newbie", owner=sam)
    nia_gift = seed.add_gift(db, nia, date(2026, 11, 1), 2550)
    db.commit()
    return dict(
        diana=diana, sam=sam, zelda=zelda, gift=gift, match=match, nia=nia, nia_gift=nia_gift
    )


def login(email: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    assert c.post("/api/app/auth/login", json={"email": email, "password": PW}).status_code == 200
    return c


def post(c: TestClient, path: str, body: dict | None = None):
    return c.post(f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies.get("cic_csrf")})


def put(c: TestClient, path: str, body: dict):
    return c.put(f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies.get("cic_csrf")})


def thank(c: TestClient, w: dict, channel: str = "email", gift: str = "gift"):
    return post(
        c, f"/donors/{w['zelda']}/messages",
        {"kind": "thank_you", "channel": channel, "gift_id": w[gift]},
    )  # fmt: skip


def count(db: Session, table: str = "messages") -> int:
    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608


# --- drafts -----------------------------------------------------------------------------------
def test_thank_you_draft_fills_the_merge_fields(w) -> None:
    r = thank(login("diana.owner@example.org"), w)
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["status"], m["kind"], m["channel"], m["gift_id"]) == (
        "draft",
        "thank_you",
        "email",
        w["gift"],
    )
    assert m["subject"] == "Thank you from Coding in Color"
    assert "Hi Zelda," in m["body"] and "$50 on November 3, 2026" in m["body"]
    assert "supporting AI Academy" in m["body"] and "Diana Owner" in m["body"]
    assert "{" not in m["body"] and m["created_by"]["display_name"] == "Diana Owner"
    assert m["approved_by"] is None and m["sent_at"] is None


def test_sms_draft_has_no_subject_and_cents_are_kept(w) -> None:
    c = login("sam.other@example.org")
    r = post(
        c, f"/donors/{w['nia']}/messages",
        {"kind": "thank_you", "channel": "sms", "gift_id": w["nia_gift"]},
    )  # fmt: skip
    assert r.status_code == 201 and r.json()["subject"] is None
    assert "$25.50" in r.json()["body"]


def test_quarterly_update_keeps_the_edit_marker_for_the_person_to_fill(w) -> None:
    r = post(login("diana.owner@example.org"), f"/donors/{w['zelda']}/messages",
             {"kind": "quarterly_update", "channel": "email"})  # fmt: skip
    assert r.status_code == 201
    assert "[EDIT:" in r.json()["body"] and r.json()["gift_id"] is None


def test_asking_twice_returns_the_same_open_draft(db: Session, w) -> None:
    c = login("diana.owner@example.org")
    first, second = thank(c, w), thank(c, w)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"] and count(db) == 1
    body = {"kind": "quarterly_update", "channel": "email"}
    a, b = (post(c, f"/donors/{w['zelda']}/messages", body) for _ in range(2))
    # the other channel is the same kind for the same donor: still one open draft
    other = post(c, f"/donors/{w['zelda']}/messages", {**body, "channel": "sms"})
    assert a.json()["id"] == b.json()["id"] == other.json()["id"] and count(db) == 2


def test_the_database_conflict_is_caught_and_returns_the_existing_draft(db: Session, w) -> None:
    """The unique index is the last line of defence when two requests race past the check."""
    actor = Actor(kind="user", id=w["diana"])
    kw = dict(donor_id=w["zelda"], gift_id=w["gift"], kind="thank_you", channel="email",
              subject="s", body="b")  # fmt: skip
    one, made = repo.insert_draft(db, actor, **kw)
    two, made_again = repo.insert_draft(db, actor, **kw)
    assert (made, made_again, one.id == two.id) == (True, False, True) and count(db) == 1


def test_a_sent_thank_you_does_not_block_a_new_open_one_for_another_gift(db: Session, w) -> None:
    other = seed.add_gift(db, w["zelda"], date(2026, 11, 10), 1000)
    db.commit()
    c = login("diana.owner@example.org")
    assert thank(c, w).status_code == 201
    r = post(c, f"/donors/{w['zelda']}/messages",
             {"kind": "thank_you", "channel": "email", "gift_id": other})  # fmt: skip
    assert r.status_code == 201 and count(db) == 2


def test_no_thank_you_draft_for_an_employer_match(db: Session, w) -> None:
    r = thank(login("diana.owner@example.org"), w, gift="match")
    assert r.status_code == 400 and "match" in r.json()["error"]["message"]
    assert count(db) == 0


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "thank_you", "channel": "email"},  # no gift
        {"kind": "thank_you", "channel": "email", "gift_id": 999999},
        {"kind": "quarterly_update", "channel": "email", "gift_id": 1},
        {"kind": "lapsed_nudge", "channel": "email"},
    ],
)
def test_bad_draft_requests_are_400(db: Session, w, body) -> None:
    r = post(login("diana.owner@example.org"), f"/donors/{w['zelda']}/messages", body)
    assert r.status_code == 400 and count(db) == 0


def test_another_donors_gift_is_refused(db: Session, w) -> None:
    r = thank(login("diana.owner@example.org"), w | {"gift": w["nia_gift"]})
    assert r.status_code == 400 and count(db) == 0


def test_do_not_contact_donors_get_no_drafts(db: Session, w) -> None:
    db.execute(text("UPDATE donors SET do_not_contact = true WHERE id = :d"), {"d": w["zelda"]})
    db.commit()
    c = login("diana.owner@example.org")
    assert thank(c, w).status_code == 409
    r = post(c, f"/donors/{w['zelda']}/messages", {"kind": "quarterly_update", "channel": "email"})
    assert r.status_code == 409 and count(db) == 0


def test_deleted_or_unknown_donor_is_404(db: Session, w) -> None:
    c = login("diana.owner@example.org")
    body = {"kind": "quarterly_update", "channel": "email"}
    assert post(c, "/donors/999999/messages", body).status_code == 404
    db.execute(text("UPDATE donors SET deleted_at = now() WHERE id = :d"), {"d": w["zelda"]})
    db.commit()
    assert post(c, f"/donors/{w['zelda']}/messages", body).status_code == 404


# --- who may draft and see ----------------------------------------------------------------------
def test_a_non_owner_gets_403_and_nothing_is_written(db: Session, w) -> None:
    r = thank(login("sam.other@example.org"), w)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert count(db) == 0


def make_super_admin(db: Session, user: int, state: str = "active") -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = :s WHERE id = 1"),
        {"u": user, "s": state},
    )
    db.commit()


def test_active_super_admin_can_draft_for_any_donor_but_a_dormant_one_cannot(
    db: Session, w
) -> None:
    make_super_admin(db, w["sam"])
    c = login("sam.other@example.org")
    assert thank(c, w).status_code == 201
    make_super_admin(db, w["sam"], "dormant")
    assert post(c, f"/donors/{w['zelda']}/messages",
                {"kind": "quarterly_update", "channel": "email"}).status_code == 403  # fmt: skip


def test_message_list_shows_only_my_donors_and_filters_by_status(db: Session, w) -> None:
    diana, sam = login("diana.owner@example.org"), login("sam.other@example.org")
    thank(diana, w)
    post(sam, f"/donors/{w['nia']}/messages", {"kind": "quarterly_update", "channel": "email"})
    mine = diana.get("/api/app/messages").json()["items"]
    assert [m["donor_name"] for m in mine] == ["Zelda Quill"]
    assert diana.get("/api/app/messages?status=sent").json()["items"] == []
    assert [m["donor_name"] for m in sam.get("/api/app/messages?status=draft").json()["items"]] == [
        "Nia Newbie"
    ]
    make_super_admin(db, w["sam"])
    assert len(sam.get("/api/app/messages").json()["items"]) == 2  # the super admin sees all


def test_logged_out_is_401_and_missing_csrf_is_403(w) -> None:
    anon = TestClient(create_app())
    assert anon.get("/api/app/messages").status_code == 401
    assert anon.get("/api/app/templates").status_code == 401
    c = login("diana.owner@example.org")
    r = c.post(
        f"/api/app/donors/{w['zelda']}/messages",
        json={"kind": "quarterly_update", "channel": "email"},
    )
    assert r.status_code == 403


def test_drafting_writes_an_audit_entry_without_the_body(db: Session, w) -> None:
    thank(login("diana.owner@example.org"), w)
    row = db.execute(
        text("SELECT data::text FROM audit_log WHERE action = 'message.draft'")
    ).scalar_one()
    assert "Zelda" not in row and "gift of" not in row and '"kind": "thank_you"' in row


# --- templates --------------------------------------------------------------------------------
def test_templates_list_the_four_built_in_ones_in_flat_mode(w) -> None:
    r = login("sam.other@example.org").get("/api/app/templates")
    assert r.status_code == 200
    items = r.json()["items"]
    assert sorted((t["kind"], t["channel"]) for t in items) == [
        ("quarterly_update", "email"), ("quarterly_update", "sms"),
        ("thank_you", "email"), ("thank_you", "sms"),
    ]  # fmt: skip
    assert items[0]["merge_fields"] == [
        "first_name", "gift_amount", "gift_date", "program", "owner_name", "org_name"
    ]  # fmt: skip


def test_an_edited_template_is_used_by_the_next_draft(w) -> None:
    c = login("diana.owner@example.org")
    tpl = {"kind": "thank_you", "channel": "email", "subject": "Hello {first_name}"}
    r = put(c, "/templates", {**tpl, "body": "Thanks {first_name} for {gift_amount}!"})
    assert r.status_code == 200 and r.json()["body"].startswith("Thanks")
    m = thank(c, w).json()
    assert (m["subject"], m["body"]) == ("Hello Zelda", "Thanks Zelda for $50!")


def test_template_with_an_unknown_field_or_kind_is_400(w) -> None:
    c = login("diana.owner@example.org")
    r = put(c, "/templates", {"kind": "thank_you", "channel": "email", "body": "Hi {donor_email}"})
    assert r.status_code == 400 and "{donor_email}" in r.json()["error"]["message"]
    r = put(c, "/templates", {"kind": "event_invite", "channel": "email", "body": "Hi"})
    assert r.status_code == 400


def test_templates_follow_governance(db: Session, w) -> None:
    make_super_admin(db, w["sam"])
    member, admin = login("diana.owner@example.org"), login("sam.other@example.org")
    body = {"kind": "thank_you", "channel": "sms", "body": "Thanks {first_name}"}
    assert member.get("/api/app/templates").status_code == 403
    assert put(member, "/templates", body).status_code == 403
    assert admin.get("/api/app/templates").status_code == 200
    assert put(admin, "/templates", body).status_code == 200
    make_super_admin(db, w["sam"], "dormant")  # flattened: everyone is equal again
    assert put(member, "/templates", body).status_code == 200


def test_template_edit_is_audited_by_id_only(db: Session, w) -> None:
    put(login("diana.owner@example.org"), "/templates",
        {"kind": "thank_you", "channel": "sms", "body": "SECRET WORDING {first_name}"})  # fmt: skip
    row = db.execute(
        text("SELECT data::text FROM audit_log WHERE action = 'template.update'")
    ).scalar_one()
    assert "SECRET" not in row
