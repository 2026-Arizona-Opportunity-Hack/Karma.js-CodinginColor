"""Create, revoke and check API keys (API-1, API-4, API-8). The full key is returned once."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.db.models import ApiKey
from app.errors import Forbidden, Invalid, Unauthorized
from app.repos import apikeys, audit
from app.security import sha256_hex

KEY_PREFIX = "cic_live_"
FULL_PREFIX = "cic_full_"
PREFIX_SHOWN = len(KEY_PREFIX) + 4  # prefix plus 4 random characters, to tell keys apart
SCOPE_AGGREGATES = "read:aggregates"
SCOPE_FULL = "full_access"
FULL_KEY_DAYS = 90  # default lifetime of a full-access key
UNAUTHORIZED = "Missing, invalid or revoked API key."


@dataclass(frozen=True)
class CreatedKey:
    row: ApiKey
    key: str


def new_key(prefix: str = KEY_PREFIX) -> str:
    """Prefix + 32 random bytes, base64url without padding (43 characters)."""
    return prefix + secrets.token_urlsafe(32)


def resolve_expiry(
    clock: Clock, scopes: list[str], *, given: bool, value: datetime | None
) -> datetime | None:
    """Full-access keys expire in 90 days unless the caller says otherwise (None = never).
    Read-only keys never expire unless asked to."""
    now = clock.now()
    if not given:
        return now + timedelta(days=FULL_KEY_DAYS) if SCOPE_FULL in scopes else None
    if value is not None and value <= now:
        raise Invalid("expires_at must be in the future.")
    return value


def create(
    db: Session,
    actor: Actor,
    *,
    name: str,
    scopes: list[str],
    created_by: int | None = None,
    expires_at: datetime | None = None,
) -> CreatedKey:
    full = SCOPE_FULL in scopes
    if full and len(set(scopes)) > 1:
        raise Invalid("A full-access key cannot carry other scopes.")
    key = new_key(FULL_PREFIX if full else KEY_PREFIX)
    row = apikeys.create(
        db,
        actor,
        name=name,
        prefix=key[:PREFIX_SHOWN],
        key_hash=sha256_hex(key),
        scopes=sorted(set(scopes)),
        created_by=created_by,
        expires_at=expires_at,
    )
    audit.write(
        db,
        actor,
        "apikey.create",
        entity="api_key",
        entity_id=row.id,
        data={"name": name, "scopes": row.scopes},
    )
    return CreatedKey(row=row, key=key)


def revoke(db: Session, clock: Clock, actor: Actor, key_id: int) -> ApiKey:
    row = apikeys.revoke(db, actor, key_id, clock.now())
    audit.write(db, actor, "apikey.revoke", entity="api_key", entity_id=row.id)
    return row


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def is_full_key_header(authorization: str | None) -> bool:
    return _bearer(authorization).startswith(FULL_PREFIX)


def _authenticate(db: Session, clock: Clock, authorization: str | None, prefix: str) -> ApiKey:
    token = _bearer(authorization)
    if not token.startswith(prefix):
        raise Unauthorized(UNAUTHORIZED)
    row = apikeys.find_by_hash(db, sha256_hex(token))
    now = clock.now()
    if (
        row is None
        or row.revoked_at is not None
        or (row.expires_at is not None and row.expires_at <= now)
    ):
        raise Unauthorized(UNAUTHORIZED)
    apikeys.touch(row, now)
    return row


def authenticate(db: Session, clock: Clock, authorization: str | None) -> ApiKey:
    """401 for a missing, malformed, unknown, revoked or expired key (docs/API.md 1.1)."""
    return _authenticate(db, clock, authorization, KEY_PREFIX)


def authenticate_full(db: Session, clock: Clock, authorization: str | None) -> ApiKey:
    """The same checks for a `cic_full_` key on /api/app, plus the full_access scope."""
    row = _authenticate(db, clock, authorization, FULL_PREFIX)
    require_scope(row, SCOPE_FULL)
    return row


def require_scope(row: ApiKey, scope: str) -> None:
    if scope not in row.scopes:
        raise Forbidden(f"This API key lacks the {scope} scope.")


def actor_for(row: ApiKey) -> Actor:
    return Actor(kind="api_key", id=row.id)
