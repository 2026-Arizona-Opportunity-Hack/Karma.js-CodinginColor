"""API-key authentication for `/api/v1`. Everything behind it needs the read:aggregates scope."""

from typing import Annotated

from fastapi import Depends, Header

from app.authz.actor import Actor
from app.db.models import ApiKey
from app.errors import TooManyRequests
from app.routes.deps import DB, ClockDep
from app.services.apikeys import ratelimit, service


def api_key(
    db: DB,
    clock: ClockDep,
    authorization: Annotated[str | None, Header()] = None,
) -> ApiKey:
    row = service.authenticate(db, clock, authorization)
    service.require_scope(row, service.SCOPE_AGGREGATES)
    wait = ratelimit.check(row.key_hash, clock.now())
    if wait is not None:
        raise TooManyRequests(
            f"Rate limit is {ratelimit.LIMIT} requests per minute.",
            headers={"Retry-After": str(wait)},
        )
    return row


ApiKeyDep = Annotated[ApiKey, Depends(api_key)]


def api_actor(row: ApiKeyDep) -> Actor:
    return service.actor_for(row)


ApiActorDep = Annotated[Actor, Depends(api_actor)]
