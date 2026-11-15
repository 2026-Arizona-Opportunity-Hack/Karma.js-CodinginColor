"""The app API contract (docs/API.md section 3): every route exists, is typed, needs a session
and CSRF like a real route, and answers 501 until its lane builds it."""

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.authz.actor import CLI
from app.clock import FixedClock, SystemClock, set_clock
from app.export_openapi import render
from app.main import create_app
from app.repos import users
from app.security import hash_password

PW = "correct horse battery"
OPENAPI_FILE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "openapi.json"

# Every route in docs/API.md section 3 (path parameters normalized to {}).
EXPECTED = {
    ("POST", "/api/app/auth/login"), ("POST", "/api/app/auth/logout"),
    ("GET", "/api/app/auth/me"), ("POST", "/api/app/auth/invite/{}/accept"),
    ("GET", "/api/app/members"), ("POST", "/api/app/members/invite"),
    ("POST", "/api/app/members/{}/deactivate"), ("POST", "/api/app/members/{}/move-donors"),
    ("GET", "/api/app/governance"), ("PUT", "/api/app/governance/scope"),
    ("POST", "/api/app/governance/flatten"),
    ("POST", "/api/app/imports/preview"), ("GET", "/api/app/imports"),
    ("GET", "/api/app/imports/{}"), ("POST", "/api/app/imports/{}/commit"),
    ("POST", "/api/app/imports/{}/reverse"),
    ("GET", "/api/app/reviews"), ("POST", "/api/app/reviews/{}/decide"),
    ("POST", "/api/app/gifts/{}/attribute"),
    ("GET", "/api/app/donors"), ("POST", "/api/app/donors"), ("GET", "/api/app/donors/{}"),
    ("PATCH", "/api/app/donors/{}"), ("DELETE", "/api/app/donors/{}"),
    ("POST", "/api/app/donors/{}/merge"), ("GET", "/api/app/donors/{}/timeline"),
    ("POST", "/api/app/donors/{}/gifts"), ("GET", "/api/app/gifts/unattributed"),
    ("POST", "/api/app/donors/{}/reassign"), ("GET", "/api/app/donors/{}/owner-history"),
    ("POST", "/api/app/donors/{}/interactions"), ("PUT", "/api/app/donors/{}/next-step"),
    ("POST", "/api/app/next-steps/{}/done"),
    ("GET", "/api/app/reminders"), ("GET", "/api/app/reminders/needs-reassignment"),
    ("POST", "/api/app/donors/{}/messages"), ("POST", "/api/app/messages/draft-quarterly"),
    ("GET", "/api/app/messages"), ("PATCH", "/api/app/messages/{}"),
    ("POST", "/api/app/messages/{}/approve"), ("POST", "/api/app/messages/{}/send"),
    ("POST", "/api/app/messages/{}/mark-sent"), ("POST", "/api/app/messages/{}/cancel"),
    ("POST", "/api/app/digest/send"),
    ("GET", "/api/app/reports/summary"), ("GET", "/api/app/reports/retention"),
    ("GET", "/api/app/reports/funder/{}"),
    ("GET", "/api/app/settings"), ("PUT", "/api/app/settings"),
    ("GET", "/api/app/templates"), ("PUT", "/api/app/templates"),
    ("GET", "/api/app/programs"), ("POST", "/api/app/programs"), ("PUT", "/api/app/programs/{}"),
    ("GET", "/api/app/program-map"), ("POST", "/api/app/program-map"),
    ("PUT", "/api/app/program-map/{}"),
    ("GET", "/api/app/api-keys"), ("POST", "/api/app/api-keys"),
    ("POST", "/api/app/api-keys/{}/revoke"),
    ("GET", "/api/app/program-outcomes"), ("POST", "/api/app/program-outcomes"),
    ("POST", "/api/app/demo/reset"),
}  # fmt: skip
IMPLEMENTED = {
    ("POST", "/api/app/gifts/{}/attribute"),  # lane A, issue #71
    ("GET", "/api/app/imports"), ("GET", "/api/app/imports/{}"),
    ("POST", "/api/app/imports/{}/commit"), ("POST", "/api/app/imports/{}/reverse"),  # lane A, #18
    ("GET", "/api/app/reviews"), ("POST", "/api/app/reviews/{}/decide"),  # lane A, issue #17
    ("POST", "/api/app/imports/preview"),  # lane A, issue #16
    ("POST", "/api/app/auth/login"), ("POST", "/api/app/auth/logout"),
    ("GET", "/api/app/auth/me"),
    ("GET", "/api/app/api-keys"), ("POST", "/api/app/api-keys"),
    ("POST", "/api/app/api-keys/{}/revoke"),  # lane C, issue #24
    ("GET", "/api/app/donors"), ("GET", "/api/app/donors/{}"),  # lane C, issue #72
    ("GET", "/api/app/donors/{}/timeline"), ("GET", "/api/app/gifts/unattributed"),
    ("POST", "/api/app/donors/{}/interactions"), ("PUT", "/api/app/donors/{}/next-step"),  # #74
    ("POST", "/api/app/next-steps/{}/done"),
    ("GET", "/api/app/reports/summary"), ("GET", "/api/app/reports/retention"),  # #26
    ("POST", "/api/app/donors/{}/messages"), ("GET", "/api/app/messages"),  # lane C, issue #36
    ("GET", "/api/app/templates"), ("PUT", "/api/app/templates"),
    ("PATCH", "/api/app/messages/{}"), ("POST", "/api/app/messages/{}/approve"),  # #37
    ("POST", "/api/app/messages/{}/cancel"),
    ("POST", "/api/app/messages/{}/send"), ("POST", "/api/app/messages/{}/mark-sent"),  # #38
    ("POST", "/api/app/donors"), ("PATCH", "/api/app/donors/{}"),  # lane C, issue #73
    ("DELETE", "/api/app/donors/{}"), ("POST", "/api/app/donors/{}/gifts"),
    ("POST", "/api/app/donors/{}/reassign"), ("GET", "/api/app/donors/{}/owner-history"),  # #29
    ("POST", "/api/app/members/{}/move-donors"),
    ("GET", "/api/app/governance"), ("PUT", "/api/app/governance/scope"),  # lane A, #31
    ("POST", "/api/app/governance/flatten"),
    ("GET", "/api/app/reminders"), ("GET", "/api/app/reminders/needs-reassignment"),  # #32
    ("GET", "/api/app/members"), ("POST", "/api/app/members/invite"),  # lane A, #30
    ("POST", "/api/app/members/{}/deactivate"), ("POST", "/api/app/auth/invite/{}/accept"),
}  # fmt: skip
PUBLIC_STUBS = {("POST", "/api/app/auth/invite/{}/accept")}

DONOR = {"kind": "person", "display_name": "Ada Lovelace"}
TODAY = "2026-11-14"
# Minimal valid JSON bodies, so validation passes and the stub answers.
BODIES: dict[tuple[str, str], dict] = {
    ("POST", "/api/app/auth/invite/{}/accept"): {"display_name": "A", "password": "x" * 12},
    ("POST", "/api/app/members/invite"): {"email": "new@example.org"},
    ("POST", "/api/app/members/{}/move-donors"): {"to_user_id": 2},
    ("PUT", "/api/app/governance/scope"): {"reassign_scope": "anyone"},
    ("POST", "/api/app/reviews/{}/decide"): {"decision": "create_new"},
    ("POST", "/api/app/gifts/{}/attribute"): {"donor_id": 2},
    ("POST", "/api/app/donors"): DONOR,
    ("PATCH", "/api/app/donors/{}"): {"notes": "hi"},
    ("POST", "/api/app/donors/{}/merge"): {"into_id": 2},
    ("POST", "/api/app/donors/{}/gifts"): {"gift_date": TODAY, "gross_cents": 5000},
    ("POST", "/api/app/donors/{}/reassign"): {"to_user_id": 2},
    ("POST", "/api/app/donors/{}/interactions"): {"kind": "call"},
    ("PUT", "/api/app/donors/{}/next-step"): {"title": "Call", "due_date": TODAY},
    ("POST", "/api/app/donors/{}/messages"): {"kind": "quarterly_update", "channel": "email"},
    ("PATCH", "/api/app/messages/{}"): {"body": "Hello"},
    ("PUT", "/api/app/settings"): {"quarterly_days": 90},
    ("PUT", "/api/app/templates"): {"kind": "thank_you", "channel": "email", "body": "Thanks"},
    ("POST", "/api/app/programs"): {"name": "Robotics"},
    ("PUT", "/api/app/programs/{}"): {"is_active": False},
    ("POST", "/api/app/program-map"): {"source": "zeffy", "source_value": "x", "program_id": 1},
    ("PUT", "/api/app/program-map/{}"): {"source": "zeffy", "source_value": "x", "program_id": 1},
    ("POST", "/api/app/program-outcomes"): {
        "program_id": 1,
        "period_start": TODAY,
        "period_end": TODAY,
        "metric_label": "Students",
        "value": "12",
        "unit": "students",
    },
    ("POST", "/api/app/api-keys"): {"name": "Dashboard"},
}
STUBS = sorted(EXPECTED - IMPLEMENTED)


@pytest.fixture(scope="module")
def logged_in(migrated: None) -> Iterator[TestClient]:
    """One login for the whole module: these routes never write, so tests can share it."""
    from app.db.session import get_engine, get_sessionmaker
    from tests.conftest import _truncate_all

    with get_engine().begin() as conn:
        _truncate_all(conn)
    set_clock(FixedClock(datetime(2026, 11, 14, 18, 0, tzinfo=UTC)))
    with get_sessionmaker()() as s:
        users.create(
            s, CLI, email="a@example.org", display_name="A", password_hash=hash_password(PW)
        )
        s.commit()
    c = TestClient(create_app(), client=("203.0.113.9", 50000))
    r = c.post("/api/app/auth/login", json={"email": "a@example.org", "password": PW})
    assert r.status_code == 200
    yield c
    set_clock(SystemClock())
    with get_engine().begin() as conn:
        _truncate_all(conn)


@pytest.fixture
def app_client(migrated: None) -> TestClient:
    """No cookies: a logged-out visitor."""
    return TestClient(create_app(), client=("203.0.113.10", 50000))


def call(c: TestClient, method: str, template: str, csrf: bool = True, **kw):
    url = template.replace("{}", "1")
    headers = {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""} if csrf else {}
    body = BODIES.get((method, template))
    if template == "/api/app/imports/preview":
        kw.update(data={"source": "zeffy"}, files={"file": ("a.csv", b"a,b\n1,2\n", "text/csv")})
    elif body is not None:
        kw["json"] = body
    return c.request(method, url, headers=headers, **kw)


def norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def test_every_route_in_the_api_doc_exists_and_nothing_else() -> None:
    schema = create_app().openapi()
    actual = {
        (m.upper(), norm(p))
        for p, ops in schema["paths"].items()
        if p.startswith("/api/app")
        for m in ops
    }
    assert actual == EXPECTED


@pytest.mark.parametrize("method,path", STUBS)
def test_stub_requires_a_session(app_client: TestClient, method: str, path: str) -> None:
    if (method, path) in PUBLIC_STUBS:
        pytest.skip("open to anyone holding an invite token")
    r = call(app_client, method, path, csrf=False)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("method,path", [s for s in STUBS if s[0] != "GET"])
def test_stub_writes_need_csrf(logged_in: TestClient, method: str, path: str) -> None:
    if (method, path) in PUBLIC_STUBS:
        pytest.skip("no session, so no CSRF")
    r = call(logged_in, method, path, csrf=False)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("method,path", STUBS)
def test_stub_answers_501_in_the_error_shape(logged_in: TestClient, method: str, path: str) -> None:
    r = call(logged_in, method, path)
    assert r.status_code == 501, r.text
    assert r.json()["error"]["code"] == "not_implemented"


def test_invalid_input_is_400_in_the_error_shape(logged_in: TestClient) -> None:
    r = logged_in.post(
        "/api/app/donors",
        json={"kind": "alien", "display_name": ""},
        headers={"X-CSRF-Token": logged_in.cookies.get("cic_csrf") or ""},
    )
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == "invalid" and "kind" in body["message"]


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "link"},  # link needs a donor
        {"decision": "create_new", "donor_id": 3},  # other decisions must not name one
    ],
)
def test_review_decision_rules_are_validated(logged_in: TestClient, body: dict) -> None:
    r = logged_in.post(
        "/api/app/reviews/1/decide",
        json=body,
        headers={"X-CSRF-Token": logged_in.cookies.get("cic_csrf") or ""},
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "person", "display_name": "x", "email": "not-an-email"},
        {"kind": "person", "display_name": "x", "phone": "call me"},
        {"kind": "person", "display_name": "x" * 201},
        {"kind": "person", "display_name": "x", "notes": "n" * 2001},
    ],
)
def test_donor_input_limits(logged_in: TestClient, bad: dict) -> None:
    r = logged_in.post(
        "/api/app/donors",
        json=bad,
        headers={"X-CSRF-Token": logged_in.cookies.get("cic_csrf") or ""},
    )
    assert r.status_code == 400


def test_gift_amount_must_be_positive_cents(logged_in: TestClient) -> None:
    r = logged_in.post(
        "/api/app/donors/1/gifts",
        json={"gift_date": TODAY, "gross_cents": 0},
        headers={"X-CSRF-Token": logged_in.cookies.get("cic_csrf") or ""},
    )
    assert r.status_code == 400


def test_documented_conflict_responses_are_in_the_schema() -> None:
    ops = create_app().openapi()["paths"]
    donors_post = ops["/api/app/donors"]["post"]["responses"]
    assert (
        "PossibleDuplicateOut"
        in donors_post["409"]["content"]["application/json"]["schema"]["$ref"]
    )
    for code in ("409", "413", "415"):
        assert code in ops["/api/app/imports/preview"]["post"]["responses"]
    assert "422" not in donors_post  # validation is 400 in our error shape


def test_funder_export_documents_html_and_csv() -> None:
    op = create_app().openapi()["paths"]["/api/app/reports/funder/{donor_id}"]["get"]
    assert set(op["responses"]["200"]["content"]) == {"text/html", "text/csv"}


def test_committed_openapi_file_is_current() -> None:
    """frontend/src/api/types.ts is generated from this file; regenerate both after a change:
    `uv run python -m app.export_openapi ../frontend/src/api/openapi.json && npm run gen:api`."""
    assert OPENAPI_FILE.read_bytes().decode("utf-8").replace("\r\n", "\n") == render()
