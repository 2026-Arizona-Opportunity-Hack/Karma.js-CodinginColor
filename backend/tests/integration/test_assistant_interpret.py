"""Assistant interpret (AST-1 to AST-3): the model proposes, nothing is written.
The gateway is stubbed with recorded replies; no network."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import CLI
from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from app.services.ai.gateway import GatewayError, get_gateway
from app.services.apikeys import ratelimit
from app.services.apikeys import service as keys
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)  # Sun 09:00 in Phoenix
WRITE_TABLES = ("interactions", "next_steps", "messages", "gifts", "donors")


class StubGateway:
    """Returns a recorded reply (or fails) and remembers what it was asked."""

    def __init__(self, reply: object = None, fail: bool = False) -> None:
        self.reply, self.fail, self.prompts = reply, fail, []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        if self.fail:
            raise GatewayError("down")
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def acts(*actions: tuple[str, dict]) -> dict:
    return {"actions": [{"tool": t, "args": a} for t, a in actions]}


@pytest.fixture(autouse=True)
def _fresh() -> Iterator[None]:
    ratelimit._hits.clear()
    set_clock(FixedClock(T0))
    yield
    set_clock(SystemClock())
    create_app().dependency_overrides.clear()


@pytest.fixture
def w(db: Session) -> dict[str, int]:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    zelda = seed.add_donor(db, "Zelda Quill", owner=diana)
    seed.add_donor(db, "Maria Lopez", owner=diana)
    seed.add_donor(db, "Maria Chen", owner=diana)
    seed.add_donor(db, "Nia Newbie", owner=sam)  # someone else's donor
    gift = seed.add_gift(db, zelda, date(2026, 11, 10), 5000)
    seed.add_donor(db, "Nora NoGift", owner=diana)
    db.execute(text("INSERT INTO app_settings (key, value) VALUES ('assistant_enabled','true')"))
    db.commit()
    return dict(diana=diana, sam=sam, zelda=zelda, gift=gift)


def ask(reply: object = None, *, fail: bool = False, as_: str = "diana", sentence: str = "hi"):
    app = create_app()
    gw = StubGateway(reply, fail)
    app.dependency_overrides[get_gateway] = lambda: gw
    c = TestClient(app, client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{as_}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    h = {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}
    return c.post("/api/app/assistant/interpret", json={"text": sentence}, headers=h), gw


def counts(db: Session) -> list[int]:
    return [db.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in WRITE_TABLES]  # noqa: S608


def test_two_intents_give_two_cards_and_write_nothing(db: Session, w) -> None:
    before = counts(db)
    r, gw = ask(
        acts(
            ("log_contact", {"donor": "Zelda", "kind": "call", "summary": "gala"}),
            (
                "create_next_step",
                {"donor": "Zelda Quill", "title": "Send invite", "due_date": "2026-11-20"},
            ),
        ),
        sentence="Called Zelda about the gala, remind me to send her the invite by the 20th",
    )
    assert r.status_code == 200, r.text
    a, b = r.json()["actions"]
    assert (a["tool"], a["status"], b["tool"], b["status"]) == (
        "log_contact", "ready", "create_next_step", "ready",
    )  # fmt: skip
    req = a["choices"][0]["request"]
    assert req["path"] == f"/api/app/donors/{w['zelda']}/interactions" and req["method"] == "POST"
    assert req["body"] == {"kind": "call", "summary": "gala"}
    assert b["choices"][0]["request"]["method"] == "PUT"
    assert "Zelda Quill" in a["summary"]
    assert counts(db) == before  # no donor data written
    audit = db.execute(
        text("SELECT data FROM audit_log WHERE action = 'assistant.interpret'")
    ).scalar_one()
    assert audit == {"actions": ["log_contact", "create_next_step"]}  # no sentence
    system, _ = gw.prompts[0]
    assert "2026-11-15" in system and "Sunday" in system
    assert "Zelda" not in system and "Maria" not in system  # donor list never sent (AST-3)


def test_unknown_tool_is_rejected_and_unclear_shows_the_question(w) -> None:
    r, _ = ask(acts(("find_donor", {"donor": "Zelda"})))
    body = r.json()
    assert body["actions"] == [] and body["message"].startswith("I can log a contact")
    r, _ = ask(acts(("unclear", {"question": "Which donor did you mean?"})))
    assert r.json()["actions"] == [] and r.json()["message"] == "Which donor did you mean?"
    r, _ = ask(acts(("create_next_step", {"donor": "Zelda"})))  # missing title and date
    assert r.json()["actions"] == [] and r.json()["message"]


def test_donor_resolution_is_limited_to_donors_you_act_on(w) -> None:
    r, _ = ask(
        acts(("log_contact", {"donor": "Nia", "kind": "call"}))
    )  # Sam's donor, asked by Diana
    (a,) = r.json()["actions"]
    assert (a["status"], a["choices"]) == ("error", []) and "Nia" in a["error"]
    r, _ = ask(acts(("log_contact", {"donor": "Maria", "kind": "call"})))
    (a,) = r.json()["actions"]
    assert a["status"] == "choose_donor"
    assert sorted(c["donor_name"] for c in a["choices"]) == ["Maria Chen", "Maria Lopez"]


def test_thank_you_uses_the_latest_gift_or_explains_there_is_none(w) -> None:
    r, _ = ask(acts(("draft_thank_you", {"donor": "Zelda"})))
    (a,) = r.json()["actions"]
    assert a["choices"][0]["request"]["body"] == {
        "kind": "thank_you", "channel": "email", "gift_id": w["gift"],
    }  # fmt: skip
    r, _ = ask(acts(("draft_thank_you", {"donor": "Nora"})))
    (a,) = r.json()["actions"]
    assert a["status"] == "error" and "no gift" in a["error"]


def test_setting_off_is_404(db: Session, w) -> None:
    db.execute(text("UPDATE app_settings SET value = 'false' WHERE key = 'assistant_enabled'"))
    db.commit()
    r, gw = ask(acts())
    assert r.status_code == 404 and gw.prompts == []


def test_gateway_down_or_garbage_is_a_friendly_503(w) -> None:
    for kwargs in ({"fail": True}, {"reply": "not json at all"}):
        r, _ = ask(**kwargs)
        assert r.status_code == 503
        assert "not available" in r.json()["error"]["message"]


def test_full_access_key_is_403(db: Session, w) -> None:
    key = keys.create(db, CLI, name="App", scopes=[keys.SCOPE_FULL], created_by=w["diana"]).key
    db.commit()
    r = TestClient(create_app(), client=("203.0.113.5", 50000)).post(
        "/api/app/assistant/interpret",
        json={"text": "hi"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 403


def test_text_over_500_chars_is_400_and_21st_request_in_a_minute_is_429(w) -> None:
    r, _ = ask(acts(), sentence="x" * 501)
    assert r.status_code == 400
    app = create_app()
    app.dependency_overrides[get_gateway] = lambda: StubGateway(acts())
    c = TestClient(app, client=("203.0.113.5", 50000))
    c.post("/api/app/auth/login", json={"email": "diana@example.org", "password": seed.PASSWORD})
    h = {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}
    codes = [
        c.post("/api/app/assistant/interpret", json={"text": "hi"}, headers=h).status_code
        for _ in range(21)
    ]
    assert codes[:20] == [200] * 20 and codes[20] == 429
