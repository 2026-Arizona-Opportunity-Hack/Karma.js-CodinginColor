"""Create, revoke and check API keys (API-1, API-4). The full key is returned once."""

import secrets
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.db.models import ApiKey
from app.errors import Forbidden, Unauthorized
from app.repos import apikeys, audit
from app.security import sha256_hex

KEY_PREFIX = "cic_live_"
PREFIX_SHOWN = len(KEY_PREFIX) + 4  # "cic_live_" plus 4 random characters, to tell keys apart
SCOPE_AGGREGATES = "read:aggregates"
UNAUTHORIZED = "Missing, invalid or revoked API key."


@dataclass(frozen=True)
class CreatedKey:
    row: ApiKey
    key: str


def new_key() -> str:
    """cic_live_ + 32 random bytes, base64url without padding (43 characters)."""
    return KEY_PREFIX + secrets.token_urlsafe(32)


def create(
    db: Session, actor: Actor, *, name: str, scopes: list[str], created_by: int | None = None
) -> CreatedKey:
    key = new_key()
    row = apikeys.create(
        db,
        actor,
        name=name,
        prefix=key[:PREFIX_SHOWN],
        key_hash=sha256_hex(key),
        scopes=sorted(set(scopes)),
        created_by=created_by,
    )
    audit.write(db, actor, "apikey.create", entity="api_key", entity_id=row.id, data={"name": name})
    return CreatedKey(row=row, key=key)


def revoke(db: Session, clock: Clock, actor: Actor, key_id: int) -> ApiKey:
    row = apikeys.revoke(db, actor, key_id, clock.now())
    audit.write(db, actor, "apikey.revoke", entity="api_key", entity_id=row.id)
    return row


def authenticate(db: Session, clock: Clock, authorization: str | None) -> ApiKey:
    """401 for a missing, malformed, unknown or revoked key (docs/API.md 1.1)."""
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token.startswith(KEY_PREFIX):
        raise Unauthorized(UNAUTHORIZED)
    row = apikeys.find_by_hash(db, sha256_hex(token))
    if row is None or row.revoked_at is not None:
        raise Unauthorized(UNAUTHORIZED)
    apikeys.touch(row, clock.now())
    return row


def require_scope(row: ApiKey, scope: str) -> None:
    if scope not in row.scopes:
        raise Forbidden(f"This API key lacks the {scope} scope.")


def actor_for(row: ApiKey) -> Actor:
    return Actor(kind="api_key", id=row.id)
