"""Full-access API keys (API-8): a `cic_full_` bearer key acts as its creating member on /api/app.

Keys are generated in fixtures through the service, so no key is ever written in this file."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.authz.actor import CLI, Actor
from app.authz.policy import NOT_FOR_KEYS, Action, can
from app.cli import main
from app.clock import FixedClock, SystemClock, set_clock
from app.db.models import ApiKey, AuditLog
from app.main import create_app
from app.services.apikeys import ratelimit
from app.services.apikeys import service as keys
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    """sam makes keys; diana owns a donor with contact details."""
    sam, diana = seed.add_user(db, "Sam"), seed.add_user(db, "Diana")
    donor = seed.add_donor(db, "Dee Donor", owner=diana, email="dee@example.org")
    db.commit()
    return dict(sam=sam, diana=diana, donor=donor)


def mint(db: Session, member: int, *, scope: str = keys.SCOPE_FULL, **kw) -> str:
    made = keys.create(db, CLI, name="Test app", scopes=[scope], created_by=member, **kw)
    db.commit()
    return made.key


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def anon() -> TestClient:
    return TestClient(create_app(), client=("203.0.113.5", 50000))


def session_client(email: str) -> TestClient:
    c = anon()
    r = c.post("/api/app/auth/login", json={"email": email, "password": seed.PASSWORD})
    assert r.status_code == 200
    return c


def make_super_admin(db: Session, user: int) -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active'"),
        {"u": user},
    )
    db.commit()


def test_key_reads_and_writes_donors_it_creator_does_not_own(db: Session, w) -> None:
    h, c = bearer(mint(db, w["sam"])), anon()
    donor = c.get(f"/api/app/donors/{w['donor']}", headers=h).json()
    assert donor["email"] == "dee@example.org"  # contact details, not owned by sam
    assert c.get("/api/app/donors", headers=h).status_code == 200

    made = c.post("/api/app/donors", json={"kind": "person", "display_name": "Ann"}, headers=h)
    assert made.status_code == 201, made.text
    patched = c.patch(f"/api/app/donors/{w['donor']}", json={"notes": "Called"}, headers=h)
    assert patched.status_code == 200 and patched.json()["notes"] == "Called"
    contact = c.post(f"/api/app/donors/{w['donor']}/interactions", json={"kind": "call"}, headers=h)
    assert contact.status_code == 201
    assert c.delete(f"/api/app/donors/{w['donor']}", headers=h).status_code == 204


def test_bad_keys_are_401(db: Session, w, clock: FixedClock) -> None:
    c, url = anon(), "/api/app/donors"
    revoked = mint(db, w["sam"])
    keys.revoke(db, clock, CLI, db.execute(select(ApiKey.id)).scalar_one())
    expired = mint(db, w["sam"], expires_at=T0 + timedelta(days=1))
    gone = mint(db, w["diana"])
    live = mint(db, w["sam"], scope=keys.SCOPE_AGGREGATES)
    db.execute(text("UPDATE users SET is_active = false WHERE id = :u"), {"u": w["diana"]})
    db.commit()
    clock.at = T0 + timedelta(days=2)

    assert c.get(url).status_code == 401  # no header
    for key in ("cic_full_" + "x" * 43, revoked, expired, gone, live):
        assert c.get(url, headers=bearer(key)).status_code == 401, key[:9]
    assert c.get(url, headers=bearer(revoked)).json()["error"]["message"] == keys.UNAUTHORIZED


def test_governance_and_key_management_are_denied_to_a_key(db: Session, w) -> None:
    make_super_admin(db, w["sam"])  # the key's creator is the active super admin
    h, c = bearer(mint(db, w["sam"])), anon()
    scope = c.put("/api/app/governance/scope", json={"reassign_scope": "own_only"}, headers=h)
    assert scope.status_code == 403
    assert c.post("/api/app/governance/flatten", headers=h).status_code == 403
    assert c.get("/api/app/api-keys", headers=h).status_code == 403
    body = {"name": "Mine", "scopes": ["full_access"]}
    assert c.post("/api/app/api-keys", json=body, headers=h).status_code == 403
    assert c.post("/api/app/api-keys/1/revoke", headers=h).status_code == 403
    assert c.post("/api/app/auth/logout", headers=h).status_code == 400
    assert c.get("/api/app/auth/me", headers=h).json()["is_super_admin"] is False


def test_csrf_is_skipped_for_keys_but_not_for_cookie_sessions(db: Session, w) -> None:
    body = {"kind": "person", "display_name": "Ann"}
    assert (
        anon().post("/api/app/donors", json=body, headers=bearer(mint(db, w["sam"]))).status_code
        == 201
    )
    cookie = session_client("sam@example.org")
    assert cookie.post("/api/app/donors", json=body).status_code == 403  # no CSRF header
    ok = cookie.post(
        "/api/app/donors", json=body, headers={"X-CSRF-Token": cookie.cookies["cic_csrf"]}
    )
    assert ok.status_code == 201


def test_audit_entries_carry_the_key_id(db: Session, w) -> None:
    key = mint(db, w["sam"])
    key_id = db.execute(select(ApiKey.id)).scalar_one()
    r = anon().post(
        "/api/app/donors", json={"kind": "person", "display_name": "Ann"}, headers=bearer(key)
    )
    assert r.status_code == 201
    entries = db.execute(select(AuditLog).where(AuditLog.action == "donor.create")).scalars().all()
    assert entries and all(e.data["api_key_id"] == key_id for e in entries)
    assert all(e.actor_id == w["sam"] for e in entries)


def test_the_301st_request_in_a_minute_gets_429(db: Session, w) -> None:
    h, c = bearer(mint(db, w["sam"])), anon()
    for _ in range(ratelimit.FULL_LIMIT):
        assert c.get("/api/app/auth/me", headers=h).status_code == 200
    over = c.get("/api/app/auth/me", headers=h)
    assert over.status_code == 429 and int(over.headers["Retry-After"]) >= 1


def test_cors_allows_any_origin_but_never_credentials() -> None:
    c = anon()
    pre = c.options(
        "/api/app/donors",
        headers={
            "Origin": "https://random-app.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "*"
    allowed = pre.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and "x-csrf-token" not in allowed
    assert "access-control-allow-credentials" not in pre.headers
    other = c.get("/healthz", headers={"Origin": "https://random-app.example"})
    assert "access-control-allow-origin" not in other.headers  # only /api/app/ is opened up


def test_a_member_creates_lists_and_revokes_a_full_access_key(db: Session, w, clock) -> None:
    c = session_client("sam@example.org")
    h = {"X-CSRF-Token": c.cookies["cic_csrf"]}
    r = c.post("/api/app/api-keys", json={"name": "CRM", "scopes": ["full_access"]}, headers=h)
    assert r.status_code == 201, r.text
    made = r.json()
    assert made["key"].startswith("cic_full_") and made["type"] == "full_access"
    assert made["expires_at"].startswith("2027-02-13")  # 90 days after T0
    never = c.post(
        "/api/app/api-keys",
        json={"name": "Forever", "scopes": ["full_access"], "expires_at": None},
        headers=h,
    ).json()
    assert never["expires_at"] is None
    row = c.get("/api/app/api-keys").json()["items"][-1]
    assert (row["type"], row["created_by_name"], "key" in row) == ("full_access", "Sam", False)
    audit = db.execute(select(AuditLog).where(AuditLog.action == "apikey.create")).scalars().first()
    assert audit is not None and audit.data["scopes"] == ["full_access"]
    assert c.post(f"/api/app/api-keys/{made['id']}/revoke", headers=h).status_code == 200
    assert anon().get("/api/app/donors", headers=bearer(made["key"])).status_code == 401


def test_only_the_super_admin_creates_keys_while_one_is_active(db: Session, w) -> None:
    make_super_admin(db, w["diana"])
    c = session_client("sam@example.org")
    r = c.post(
        "/api/app/api-keys",
        json={"name": "CRM", "scopes": ["full_access"]},
        headers={"X-CSRF-Token": c.cookies["cic_csrf"]},
    )
    assert r.status_code == 403


def test_the_cli_creates_a_full_access_key(db: Session, w, capsys) -> None:
    code = main(
        ["apikey", "create", "--scope", "full_access", "--name", "Ops", "--as", "sam@example.org"]
    )
    assert code == 0 and "cic_full_" in capsys.readouterr().out
    row = db.execute(select(ApiKey)).scalar_one()
    assert (row.scopes, row.created_by) == (["full_access"], w["sam"])
    assert row.expires_at is not None


def test_policy_gives_a_full_access_actor_everything_but_governance_and_keys() -> None:
    key = Actor(kind="user", id=1, full_access=True, api_key_id=7)
    denied = NOT_FOR_KEYS | {Action.APIKEY_MANAGE}
    assert all(can(key, a) is (a not in denied) for a in Action)
    assert not any(can(key, a) for a in denied)
