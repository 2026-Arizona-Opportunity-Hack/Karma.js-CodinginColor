"""API keys. Only the SHA-256 of a key is stored (API-1). Managing keys needs `apikey.manage`;
looking a key up by its hash happens before any Actor exists, so that part takes none."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import ApiKey
from app.errors import Forbidden, NotFound

LAST_USED_GRANULARITY = timedelta(seconds=60)  # avoid a write on every request


def _require_manage(actor: Actor) -> None:
    if not can(actor, Action.APIKEY_MANAGE):
        raise Forbidden("You are not allowed to manage API keys.")


def create(
    db: Session,
    actor: Actor,
    *,
    name: str,
    prefix: str,
    key_hash: str,
    scopes: list[str],
    created_by: int | None = None,
) -> ApiKey:
    """A member creates keys as themselves. The setup CLI names the member it acts for."""
    _require_manage(actor)
    owner = created_by if actor.kind == "cli" else actor.user_id
    if owner is None:
        raise Forbidden("API keys are created by a signed-in member.")
    row = ApiKey(name=name, prefix=prefix, key_hash=key_hash, scopes=scopes, created_by=owner)
    db.add(row)
    db.flush()
    return row


def list_all(db: Session, actor: Actor) -> list[ApiKey]:
    _require_manage(actor)
    return list(db.execute(select(ApiKey).order_by(ApiKey.id.desc())).scalars())


def revoke(db: Session, actor: Actor, key_id: int, at: datetime) -> ApiKey:
    _require_manage(actor)
    row = db.get(ApiKey, key_id)
    if row is None:
        raise NotFound("API key not found.")
    if row.revoked_at is None:  # revoking twice keeps the first time
        row.revoked_at = at
    return row


def find_by_hash(db: Session, key_hash: str) -> ApiKey | None:
    """Pre-auth lookup for the public API. The caller rejects revoked keys."""
    return db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash)).scalar_one_or_none()


def touch(row: ApiKey, now: datetime) -> None:
    if row.last_used_at is None or now - row.last_used_at >= LAST_USED_GRANULARITY:
        row.last_used_at = now
