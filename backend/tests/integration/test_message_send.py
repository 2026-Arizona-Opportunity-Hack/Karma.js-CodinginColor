# ruff: noqa: F811 (the fixtures come from tests.msgkit and are used as arguments)
"""Sending (MSG-3 to MSG-7): dry run, live email through an injected transport, texts marked
sent by hand, the hash check, the double-send race, and what every send writes."""

import threading
import time
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import FixedClock
from app.db.session import get_sessionmaker
from app.errors import Conflict
from app.main import create_app
from app.routes.app_messages import http_client, mail_config
from app.services.messaging import send as sender
from app.services.messaging.mailer import MailConfig
from tests.msgkit import clock, draft, login, make_super_admin, post, row, w  # noqa: F401

DIANA = "diana.owner@example.org"
SAM = "sam.other@example.org"
KEY = "re_TESTKEY_never_real"


class Net:
    """An httpx transport that records requests; with no handler it fails if it is used."""

    def __init__(self, handler=None) -> None:
        self.requests: list[httpx.Request] = []
        self.handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.handler is None:
            raise AssertionError("the network was used")
        return self.handler(request)

    def overrides(
        self, mode: str, *, key: str = KEY, sender_: str = "CIC <hi@example.org>"
    ) -> dict:
        cfg = MailConfig(mode=mode, api_key=key, mail_from=sender_)
        client = httpx.Client(transport=httpx.MockTransport(self))
        return {mail_config: lambda: cfg, http_client: lambda: client}


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": "re_abc123"})


def approved_email(c: TestClient, w) -> dict:
    m = draft(c, w)
    assert post(c, f"/messages/{m['id']}/approve").status_code == 200
    return m


# --- dry run: acceptance test 9 -----------------------------------------------------------------
def test_dry_run_thank_you_draft_approve_send_and_it_makes_no_network_call(db: Session, w) -> None:
    net = Net()  # fails if used
    c = login(DIANA, net.overrides("dry_run"))
    m = approved_email(c, w)
    r = post(c, f"/messages/{m['id']}/send")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "sent" and out["delivery_mode"] == "dry_run"
    assert (
        out["provider_ref"] == f"dry-run-{m['id']}"
        and out["sent_by"]["display_name"] == "Diana Owner"
    )
    assert out["sent_at"].startswith("2026-11-15T16:00")
    assert net.requests == []  # no network call at all
    stored = row(db, m["id"])
    assert stored["status"] == "sent" and stored["approved_by"] == w["diana"]


def test_a_send_writes_history_a_timeline_entry_and_an_audit_entry(db: Session, w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = draft(c, w, text_body="PRIVATE THANK YOU TEXT")
    post(c, f"/messages/{m['id']}/approve")
    post(c, f"/messages/{m['id']}/send")
    it = (
        db.execute(text("SELECT * FROM interactions WHERE message_id = :m"), {"m": m["id"]})
        .mappings()
        .one()
    )
    assert (it["kind"], it["donor_id"], it["gift_id"], it["user_id"]) == (
        "thank_you", w["zelda"], w["gift"], w["diana"]
    )  # fmt: skip
    assert str(it["occurred_on"]) == "2026-11-15" and "PRIVATE" not in it["summary"]
    a = db.execute(text("SELECT * FROM audit_log WHERE action = 'message.send'")).mappings().one()
    assert a["actor_id"] == w["diana"] and a["entity_id"] == m["id"]
    assert a["data"]["mode"] == "dry_run" and a["data"]["channel"] == "email"
    assert "PRIVATE" not in str(a["data"]) and "Zelda" not in str(a["data"])
    # the timeline shows the sent message once, not the interaction as well
    kinds = [t["kind"] for t in c.get(f"/api/app/donors/{w['zelda']}/timeline").json()["items"]]
    assert kinds.count("message") == 1 and "contact" not in kinds


def test_a_quarterly_update_is_logged_as_an_update_without_a_gift(db: Session, w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    q = post(
        c, f"/donors/{w['zelda']}/messages", {"kind": "quarterly_update", "channel": "email"}
    ).json()
    c.patch(f"/api/app/messages/{q['id']}", json={"body": "A quarter of news."},
            headers={"X-CSRF-Token": c.cookies.get("cic_csrf")})  # fmt: skip
    post(c, f"/messages/{q['id']}/approve")
    assert post(c, f"/messages/{q['id']}/send").status_code == 200
    it = db.execute(
        text("SELECT kind, gift_id FROM interactions WHERE message_id = :m"), {"m": q["id"]}
    ).one()
    assert tuple(it) == ("update", None)


def test_sending_a_draft_is_409_and_records_nothing(db: Session, w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = draft(c, w)
    r = post(c, f"/messages/{m['id']}/send")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert row(db, m["id"])["status"] == "draft"
    assert db.execute(text("SELECT count(*) FROM interactions")).scalar_one() == 0


def test_editing_after_approval_returns_to_draft_so_send_is_409(w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = approved_email(c, w)
    c.patch(f"/api/app/messages/{m['id']}", json={"body": "new words"},
            headers={"X-CSRF-Token": c.cookies.get("cic_csrf")})  # fmt: skip
    assert post(c, f"/messages/{m['id']}/send").status_code == 409


@pytest.mark.parametrize("status", ["cancelled", "failed", "sent", "sent_manually"])
def test_only_approved_can_be_sent(db: Session, w, status) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = draft(c, w)
    db.execute(
        text("UPDATE messages SET status = :s, approved_by = created_by, approved_at = now(), "
             "body_sha256_at_approval = 'h', sent_at = now() WHERE id = :i"),
        {"s": status, "i": m["id"]},
    )  # fmt: skip
    db.commit()
    assert post(c, f"/messages/{m['id']}/send").status_code == 409
    assert post(c, f"/messages/{m['id']}/mark-sent").status_code == 409


def test_a_second_send_is_409_and_writes_one_timeline_entry(db: Session, w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = approved_email(c, w)
    assert post(c, f"/messages/{m['id']}/send").status_code == 200
    assert post(c, f"/messages/{m['id']}/send").status_code == 409
    assert db.execute(text("SELECT count(*) FROM interactions")).scalar_one() == 1


def test_a_changed_body_is_refused_at_send_even_if_the_status_says_approved(db: Session, w) -> None:
    net = Net(ok)
    c = login(DIANA, net.overrides("live"))
    m = approved_email(c, w)
    db.execute(text("UPDATE messages SET body = 'tampered' WHERE id = :i"), {"i": m["id"]})
    db.commit()
    r = post(c, f"/messages/{m['id']}/send")
    assert r.status_code == 409 and "changed after approval" in r.json()["error"]["message"]
    assert net.requests == [] and row(db, m["id"])["status"] == "approved"
    assert db.execute(text("SELECT count(*) FROM interactions")).scalar_one() == 0


def test_do_not_contact_after_approval_blocks_the_send(db: Session, w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = approved_email(c, w)
    db.execute(text("UPDATE donors SET do_not_contact = true WHERE id = :d"), {"d": w["zelda"]})
    db.commit()
    assert post(c, f"/messages/{m['id']}/send").status_code == 409
    assert row(db, m["id"])["status"] == "approved"


# --- the double-send race --------------------------------------------------------------------
def test_two_simultaneous_sends_produce_one_send(db: Session, w) -> None:
    m = approved_email(login(DIANA), w)
    hits: list[int] = []

    def slow(request: httpx.Request) -> httpx.Response:
        hits.append(1)
        time.sleep(0.5)  # hold the row lock long enough for the other request to arrive
        return httpx.Response(200, json={"id": "re_once"})

    cfg = MailConfig(mode="live", api_key=KEY, mail_from="CIC <hi@example.org>")
    clock = FixedClock(datetime(2026, 11, 15, 16, 0, tzinfo=UTC))
    actor = Actor(kind="user", id=w["diana"])
    results: list[str] = []

    def attempt() -> None:
        with get_sessionmaker()() as s, httpx.Client(transport=httpx.MockTransport(slow)) as client:
            try:
                sender.send_email(s, clock, actor, m["id"], cfg=cfg, client=client)
                s.commit()
                results.append("sent")
            except Conflict:
                s.rollback()
                results.append("conflict")

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["conflict", "sent"] and len(hits) == 1
    assert db.execute(text("SELECT count(*) FROM interactions")).scalar_one() == 1
    assert (
        db.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'message.send'")
        ).scalar_one()
        == 1
    )


# --- live email (through an injected transport; no real key, no real network) -------------------
def test_live_send_posts_to_resend_with_the_key_and_records_the_reference(db: Session, w) -> None:
    net = Net(ok)
    c = login(DIANA, net.overrides("live"))
    m = approved_email(c, w)
    out = post(c, f"/messages/{m['id']}/send").json()
    assert (out["status"], out["delivery_mode"], out["provider_ref"]) == (
        "sent",
        "live",
        "re_abc123",
    )
    (req,) = net.requests
    assert str(req.url) == "https://api.resend.com/emails"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    sent = httpx.Response(200, content=req.content).json()
    assert sent["to"] == ["zelda@pii.test"] and sent["from"] == "CIC <hi@example.org>"
    assert sent["text"] == "Hello Zelda" and sent["subject"].startswith("Thank you")


@pytest.mark.parametrize(
    "handler,expected",
    [
        (lambda r: httpx.Response(422, text="bad: Hello Zelda re_TESTKEY_never_real"),
         "The mail provider refused the message (HTTP 422)."),
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("boom to api.resend.com")),
         "Could not reach the mail provider."),
    ],
)  # fmt: skip
def test_a_provider_failure_sets_failed_with_a_short_error_and_never_retries(
    db: Session, w, handler, expected
) -> None:
    net = Net(handler)
    c = login(DIANA, net.overrides("live"))
    m = approved_email(c, w)
    r = post(c, f"/messages/{m['id']}/send")
    assert r.status_code == 200 and r.json()["status"] == "failed" and r.json()["error"] == expected
    stored = row(db, m["id"])
    assert stored["status"] == "failed" and stored["sent_at"] is None and stored["sent_by"] is None
    assert len(net.requests) == 1
    assert post(c, f"/messages/{m['id']}/send").status_code == 409  # no retry, even by hand
    assert len(net.requests) == 1
    assert (
        db.execute(text("SELECT count(*) FROM interactions")).scalar_one() == 0
    )  # nothing was sent
    blob = " ".join(str(x) for x in db.execute(text("SELECT data::text FROM audit_log")).scalars())
    assert KEY not in blob + expected and "Hello Zelda" not in blob + expected


def test_live_mode_without_a_key_sends_nothing(db: Session, w) -> None:
    net = Net(ok)
    c = login(DIANA, net.overrides("live", key=""))
    m = approved_email(c, w)
    r = post(c, f"/messages/{m['id']}/send")
    assert r.status_code == 409 and "not set up" in r.json()["error"]["message"]
    assert net.requests == [] and row(db, m["id"])["status"] == "approved"


def test_the_key_never_appears_in_a_response_or_the_config_repr(w) -> None:
    cfg = MailConfig(mode="live", api_key=KEY, mail_from="x")
    assert KEY not in repr(cfg)
    c = login(DIANA, Net(ok).overrides("live"))
    m = approved_email(c, w)
    assert KEY not in post(c, f"/messages/{m['id']}/send").text


# --- texts ----------------------------------------------------------------------------------
def test_an_approved_text_has_an_sms_link_and_mark_sent_records_it(db: Session, w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = draft(c, w, channel="sms", text_body="Thank you, Zelda & friends!")
    assert m["sms_link"] is None  # only once approved
    out = post(c, f"/messages/{m['id']}/approve").json()
    assert out["sms_link"] == "sms:+15550100?body=Thank%20you%2C%20Zelda%20%26%20friends%21"
    assert post(c, f"/messages/{m['id']}/send").status_code == 400  # a text is not sent by the app
    done = post(c, f"/messages/{m['id']}/mark-sent").json()
    assert (done["status"], done["delivery_mode"], done["provider_ref"]) == (
        "sent_manually",
        "manual",
        None,
    )
    assert done["sent_by"]["display_name"] == "Diana Owner" and done["sms_link"] is None
    it = db.execute(text("SELECT kind, message_id, gift_id FROM interactions")).one()
    assert tuple(it) == ("thank_you", m["id"], w["gift"])
    assert post(c, f"/messages/{m['id']}/mark-sent").status_code == 409


def test_mark_sent_is_only_for_approved_texts(w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    sms = draft(c, w, channel="sms", gift="gift2")
    assert post(c, f"/messages/{sms['id']}/mark-sent").status_code == 409  # still a draft
    email = approved_email(c, w)
    assert post(c, f"/messages/{email['id']}/mark-sent").status_code == 400


def test_the_sms_link_is_for_the_owner_only(db: Session, w) -> None:
    m = draft(login(DIANA), w, channel="sms")
    post(login(DIANA), f"/messages/{m['id']}/approve")
    assert login(SAM).get("/api/app/messages").json()["items"] == []  # not visible to others
    assert (
        "sms:"
        in login(DIANA).get("/api/app/messages?status=approved").json()["items"][0]["sms_link"]
    )


# --- who may send ------------------------------------------------------------------------------
def test_a_non_owner_cannot_send_or_mark_sent(db: Session, w) -> None:
    m = approved_email(login(DIANA), w)
    s = draft(login(DIANA), w, channel="sms", gift="gift2")
    post(login(DIANA), f"/messages/{s['id']}/approve")
    sam = login(SAM, Net().overrides("dry_run"))
    for path in (f"/messages/{m['id']}/send", f"/messages/{s['id']}/mark-sent"):
        r = post(sam, path)
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert row(db, m["id"])["status"] == "approved" and row(db, s["id"])["status"] == "approved"
    assert db.execute(text("SELECT count(*) FROM interactions")).scalar_one() == 0


def test_an_active_super_admin_can_send_for_anyone_a_dormant_one_cannot(db: Session, w) -> None:
    m = approved_email(login(DIANA), w)
    make_super_admin(db, w["sam"])
    sam = login(SAM, Net().overrides("dry_run"))
    out = post(sam, f"/messages/{m['id']}/send").json()
    assert (
        out["sent_by"]["display_name"] == "Sam Other"
        and out["approved_by"]["display_name"] == "Diana Owner"
    )
    other = approved_email(login(DIANA), w)  # a sent thank-you frees the gift for a new one
    make_super_admin(db, w["sam"], "dormant")
    assert post(sam, f"/messages/{other['id']}/send").status_code == 403


def test_send_and_mark_sent_need_a_session_and_csrf(w) -> None:
    m = approved_email(login(DIANA), w)
    anon = TestClient(create_app())
    for path in ("send", "mark-sent"):
        assert anon.post(f"/api/app/messages/{m['id']}/{path}").status_code == 401
        assert login(DIANA).post(f"/api/app/messages/{m['id']}/{path}").status_code == 403


def test_send_history_lists_who_when_channel_mode_and_reference(w) -> None:
    c = login(DIANA, Net().overrides("dry_run"))
    m = approved_email(c, w)
    post(c, f"/messages/{m['id']}/send")
    (item,) = c.get("/api/app/messages?status=sent").json()["items"]
    assert (item["sent_by"]["display_name"], item["channel"], item["delivery_mode"]) == (
        "Diana Owner", "email", "dry_run"
    )  # fmt: skip
    assert item["sent_at"] and item["provider_ref"] == f"dry-run-{m['id']}"


def test_sending_a_thank_you_clears_its_reminder(w) -> None:
    """Acceptance test 9, last step: the reminders service reads the interaction we write."""
    c = login(DIANA, Net().overrides("dry_run"))

    def due() -> list[int | None]:
        items = c.get("/api/app/reminders").json()["items"]
        return [i["gift_id"] for i in items if i["type"] == "thank_you_due"]

    assert w["gift"] in due()
    m = approved_email(c, w)
    post(c, f"/messages/{m['id']}/send")
    assert w["gift"] not in due() and w["gift2"] in due()  # only that gift was thanked
