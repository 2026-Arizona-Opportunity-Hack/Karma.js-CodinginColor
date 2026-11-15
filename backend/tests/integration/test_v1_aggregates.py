"""Public read API: aggregates, rate limit, errors, and no donor PII (acceptance test 12)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)  # Sun 09:00 in Phoenix
PII_NAME, PII_EMAIL, PII_PHONE, PII_NOTE = (
    "Zelda Quillfeather",
    "zelda@pii.test",
    "+15551230000",
    "likes owls",
)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def world(db: Session, clock: FixedClock) -> dict:
    diana = seed.add_user(db, "Diana Board")
    sam = seed.add_user(db, "Sam Board")
    zelda = seed.add_donor(
        db, PII_NAME, owner=diana, email=PII_EMAIL, phone=PII_PHONE, notes=PII_NOTE
    )
    omar = seed.add_donor(db, "Omar Other", owner=sam)
    gone = seed.add_donor(db, "Deleted Dan", owner=sam, deleted=True)
    seed.add_gift(db, zelda, date(2026, 10, 3), 10_000, program="AI Academy", fee=300)
    seed.add_gift(db, zelda, date(2026, 11, 2), 5_000, program="AI Academy")
    seed.add_gift(db, omar, date(2026, 11, 2), 2_500, program="Summer Camp")
    seed.add_gift(db, None, date(2026, 11, 10), 1_000)  # anonymous: counts in org totals
    seed.add_gift(db, None, date(2026, 11, 10), 9_999, attribution="pending_review")  # never
    seed.add_gift(db, omar, date(2026, 11, 10), 7_777, deleted=True)  # never
    seed.add_gift(db, gone, date(2026, 11, 11), 100)  # donor deleted, gift stays in org totals
    seed.add_gift(db, omar, date(2024, 1, 5), 4_000)  # outside the default range
    seed.add_interaction(db, zelda, diana, date(2026, 11, 14), "call")
    seed.add_interaction(db, zelda, diana, date(2026, 11, 14), "note")
    seed.add_interaction(db, omar, sam, date(2026, 11, 14), "system")  # not a contact
    seed.add_sent_message(
        db, zelda, diana, datetime(2026, 11, 14, 5, 0, tzinfo=UTC)
    )  # 13 Nov 22:00
    key = seed.add_api_key(db, diana)
    db.commit()
    return {"key": key, "diana": diana, "sam": sam, "db": db}


def api(world: dict) -> TestClient:
    return TestClient(create_app(), headers={"Authorization": f"Bearer {world['key']}"})


def test_by_program_totals_and_envelope(world) -> None:
    r = api(world).get(
        "/api/v1/totals/by-program", params={"from": "2025-11-01", "to": "2026-11-15"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "USD" and body["as_of"].startswith("2026-11-15T16:00:00")
    assert body["from"] == "2025-11-01" and body["to"] == "2026-11-15"
    assert body["items"] == [
        {"program": "AI Academy", "gross_cents": 15_000, "gift_count": 2, "donor_count": 1},
        {"program": "Summer Camp", "gross_cents": 2_500, "gift_count": 1, "donor_count": 1},
        {"program": "General", "gross_cents": 1_100, "gift_count": 2, "donor_count": 1},
    ]


def test_by_period_month_quarter_year(world) -> None:
    c = api(world)
    month = c.get("/api/v1/totals/by-period", params={"from": "2026-01-01", "to": "2026-12-31"})
    assert month.json()["period"] == "month"
    assert month.json()["items"] == [
        {"period_start": "2026-10-01", "gross_cents": 10_000, "net_cents": 9_700,
         "gift_count": 1, "donor_count": 1},
        {"period_start": "2026-11-01", "gross_cents": 8_600, "net_cents": 8_600,
         "gift_count": 4, "donor_count": 3},
    ]  # fmt: skip
    year = c.get("/api/v1/totals/by-period", params={"period": "year", "from": "2024-01-01"})
    assert [(i["period_start"], i["gross_cents"]) for i in year.json()["items"]] == [
        ("2024-01-01", 4_000),
        ("2026-01-01", 18_600),
    ]
    q = c.get("/api/v1/totals/by-period", params={"period": "quarter", "from": "2026-01-01"})
    assert [i["period_start"] for i in q.json()["items"]] == ["2026-10-01"]


def test_by_board_member(world) -> None:
    body = api(world).get("/api/v1/totals/by-board-member", params={"from": "2026-11-01"}).json()
    assert body["items"] == [
        {"board_member": "Diana Board", "donors_owned": 1, "gross_cents": 5_000,
         "open_reminders": 0, "contacts_logged": 2, "messages_sent": 1},
        {"board_member": "Sam Board", "donors_owned": 1, "gross_cents": 2_500,
         "open_reminders": 0, "contacts_logged": 0, "messages_sent": 0},
    ]  # fmt: skip


def test_recent_activity_lists_every_day(world) -> None:
    body = api(world).get("/api/v1/activity/recent", params={"days": 7}).json()
    days = {d["day"]: d for d in body["items"]}
    assert next(iter(days)) == "2026-11-09" and list(days)[-1] == "2026-11-15" and len(days) == 7
    assert days["2026-11-10"] == {
        "day": "2026-11-10", "gifts_received": 1, "gross_cents": 1_000,
        "contacts_logged": 0, "messages_sent": 0,
    }  # fmt: skip
    assert days["2026-11-13"]["messages_sent"] == 1  # 05:00 UTC is still the 13th in Phoenix
    assert days["2026-11-14"]["contacts_logged"] == 2
    assert days["2026-11-12"]["gifts_received"] == 0


ENDPOINTS = [
    "/api/v1/totals/by-period",
    "/api/v1/totals/by-program",
    "/api/v1/totals/by-board-member",
    "/api/v1/activity/recent",
]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_no_key_wrong_key_and_revoked_key_get_401(world, path) -> None:
    anon = TestClient(create_app())
    assert anon.get(path).status_code == 401
    wrong = anon.get(path, headers={"Authorization": "Bearer cic_live_" + "Z" * 43})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "unauthorized"
    db: Session = world["db"]
    db.execute(__import__("sqlalchemy").text("UPDATE api_keys SET revoked_at = now()"))
    db.commit()
    assert api(world).get(path).status_code == 401


def test_rate_limit_is_60_per_minute_per_key_with_retry_after(world, clock) -> None:
    c = api(world)
    for _ in range(60):
        assert c.get("/api/v1/totals/by-program").status_code == 200
    r = c.get("/api/v1/totals/by-program")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "too_many_requests"
    assert r.headers["retry-after"] == "60"
    clock.at = T0 + timedelta(seconds=45)
    assert c.get("/api/v1/totals/by-program").headers["retry-after"] == "15"
    clock.at = T0 + timedelta(seconds=61)
    assert c.get("/api/v1/totals/by-program").status_code == 200


def test_responses_contain_no_donor_pii(world) -> None:
    c = api(world)
    text = "".join(c.get(p).text for p in ENDPOINTS)
    for secret in (PII_NAME, PII_EMAIL, PII_PHONE, PII_NOTE, "Omar", "Deleted Dan"):
        assert secret not in text


# --- acceptance test 12: the OpenAPI schema itself has no donor PII fields -----------------
FORBIDDEN = {
    "id", "donor", "donors", "name", "display_name", "first_name", "last_name", "full_name",
    "email", "phone", "note", "notes", "address", "payer_name", "organization",
}  # fmt: skip


def _resolve(schema: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if ref:
        target: dict = schema
        for part in ref.removeprefix("#/").split("/"):
            target = target[part]
        return target
    return node


def _field_names(schema: dict, node: dict, seen: set[str]) -> set[str]:
    node = _resolve(schema, node)
    names: set[str] = set()
    for sub in node.get("anyOf", []) + node.get("allOf", []) + node.get("oneOf", []):
        names |= _field_names(schema, sub, seen)
    if "items" in node:
        names |= _field_names(schema, node["items"], seen)
    if isinstance(node.get("additionalProperties"), dict):
        names |= _field_names(schema, node["additionalProperties"], seen)
    for name, prop in node.get("properties", {}).items():
        # `donors` as a plain count (retention classes) is fine; a list of donors is not.
        if not (name == "donors" and _resolve(schema, prop).get("type") == "integer"):
            names.add(name)
        names |= _field_names(schema, prop, seen)
    return names


def test_openapi_for_v1_has_no_donor_pii_fields() -> None:
    schema = create_app().openapi()
    v1 = {p: ops for p, ops in schema["paths"].items() if p.startswith("/api/v1")}
    assert len(v1) >= 5
    names: set[str] = set()
    for ops in v1.values():
        for op in ops.values():
            for resp in op["responses"].values():
                body = resp.get("content", {}).get("application/json", {}).get("schema")
                if body:
                    names |= _field_names(schema, body, set())
            for param in op.get("parameters", []):
                names.add(param["name"])
    assert names, "walker found nothing, so it proves nothing"
    assert not (names & FORBIDDEN), names & FORBIDDEN
    assert not [n for n in names if n.endswith("_id")], names
    assert {"board_member", "program", "gross_cents"} <= names  # the walker does see fields
