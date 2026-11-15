"""API keys (API-1): format, hashing, scope, revoke, policy, and /api/v1 key auth."""

import base64
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.authz.actor import CLI
from app.clock import FixedClock, SystemClock, set_clock
from app.db.models import ApiKey, AuditLog
from app.main import create_app
from app.repos import users
from app.routes.v1.auth import ApiKeyDep
from app.security import hash_password

PW = "correct horse battery"
T0 = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def members(db: Session) -> dict[str, int]:
    out = {}
    for email, name in [("diana@example.org", "Diana"), ("sam@example.org", "Sam")]:
        u = users.create(db, CLI, email=email, display_name=name, password_hash=hash_password(PW))
        out[email] = u.id
    db.commit()
    return out


def app_with_probe() -> FastAPI:
    """The real app plus a probe route behind the API-key dependency (real v1 routes: #25)."""
    app = create_app()
    probe = APIRouter()

    @probe.get("/api/v1/_probe")
    def _probe(key: ApiKeyDep) -> dict[str, int]:
        return {"key_id": key.id}

    app.include_router(probe)
    return app


def member_client(email: str) -> TestClient:
    c = TestClient(app_with_probe(), client=("203.0.113.5", 50000))
    assert c.post("/api/app/auth/login", json={"email": email, "password": PW}).status_code == 200
    return c


def csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("cic_csrf") or ""}


def make_key(c: TestClient, name: str = "Dashboard") -> dict:
    r = c.post("/api/app/api-keys", json={"name": name}, headers=csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_key_format_is_32_random_bytes_base64url(db: Session, clock, members) -> None:
    key = make_key(member_client("diana@example.org"))["key"]
    assert key.startswith("cic_live_")
    body = key.removeprefix("cic_live_")
    assert len(body) == 43 and "=" not in body
    assert len(base64.urlsafe_b64decode(body + "=")) == 32


def test_only_sha256_is_stored_and_key_is_shown_once(db: Session, clock, members) -> None:
    c = member_client("diana@example.org")
    created = make_key(c)
    stored = db.execute(select(ApiKey)).scalar_one()
    assert stored.key_hash == hashlib.sha256(created["key"].encode()).hexdigest()
    assert created["key"] not in (stored.key_hash, stored.prefix, stored.name)
    assert created["prefix"] == created["key"][:13] == stored.prefix
    assert created["scopes"] == ["read:aggregates"]
    listing = c.get("/api/app/api-keys")
    assert len(listing.json()["items"]) == 1 and "key" not in listing.json()["items"][0]
    assert created["key"] not in listing.text


def test_valid_key_reaches_v1_and_records_last_used(db: Session, clock, members) -> None:
    c = member_client("diana@example.org")
    key = make_key(c)["key"]
    assert c.get("/api/v1/_probe").status_code == 401  # a session cookie is not a key
    assert c.get("/api/v1/_probe", headers=bearer(key)).status_code == 200
    db.expire_all()
    assert db.execute(select(ApiKey.last_used_at)).scalar_one() == T0
    assert c.get("/api/app/api-keys").json()["items"][0]["last_used_at"] is not None


def test_revoked_key_gets_401_and_revoke_is_audited(db: Session, clock, members) -> None:
    c = member_client("diana@example.org")
    made = make_key(c)
    assert c.get("/api/v1/_probe", headers=bearer(made["key"])).status_code == 200
    r = c.post(f"/api/app/api-keys/{made['id']}/revoke", headers=csrf(c))
    assert r.status_code == 200 and r.json()["revoked_at"] is not None
    assert c.get("/api/v1/_probe", headers=bearer(made["key"])).status_code == 401
    again = c.post(f"/api/app/api-keys/{made['id']}/revoke", headers=csrf(c)).json()
    assert again["revoked_at"] == r.json()["revoked_at"]  # revoking twice keeps the first time
    actions = db.execute(select(AuditLog.action).order_by(AuditLog.id)).scalars().all()
    assert "apikey.create" in actions and actions.count("apikey.revoke") == 2


def _activate_super_admin(db: Session, user_id: int) -> None:
    db.execute(
        text(
            "UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
            "WHERE id = 1"
        ),
        {"u": user_id},
    )
    db.commit()


def test_with_an_active_super_admin_only_they_manage_keys(db: Session, clock, members) -> None:
    sam = member_client("sam@example.org")
    made = make_key(sam)  # flat mode: any member may
    _activate_super_admin(db, members["diana@example.org"])
    revoke = f"/api/app/api-keys/{made['id']}/revoke"
    assert sam.get("/api/app/api-keys").status_code == 403
    assert sam.post("/api/app/api-keys", json={"name": "x"}, headers=csrf(sam)).status_code == 403
    assert sam.post(revoke, headers=csrf(sam)).status_code == 403
    diana = member_client("diana@example.org")
    assert diana.get("/api/app/api-keys").status_code == 200
    assert make_key(diana, "Dash 2")["name"] == "Dash 2"
    assert diana.post(revoke, headers=csrf(diana)).status_code == 200
