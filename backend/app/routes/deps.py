"""Request dependencies: session auth and CSRF for every /api/app route."""

import ipaddress
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, get_clock
from app.db.models import SessionRow, User
from app.db.session import get_db
from app.errors import Forbidden, Unauthorized
from app.repos import users
from app.services.auth import service

SESSION_COOKIE = "cic_session"
CSRF_COOKIE = "cic_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DB = Annotated[Session, Depends(get_db)]
ClockDep = Annotated[Clock, Depends(get_clock)]


def client_ip(request: Request) -> str | None:
    """A valid IP or None. uvicorn --proxy-headers puts the real client here behind Render."""
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


@dataclass(frozen=True)
class Current:
    actor: Actor
    user: User
    session: SessionRow


def current(request: Request, db: DB, clock: ClockDep) -> Current:
    found = service.resolve(db, clock, request.cookies.get(SESSION_COOKIE))
    if found is None:
        db.commit()  # persist any revocation done while resolving
        raise Unauthorized("Please log in.")
    row, user = found
    if request.method not in SAFE_METHODS and not service.csrf_ok(
        row, request.headers.get(CSRF_HEADER), request.cookies.get(CSRF_COOKIE)
    ):
        raise Forbidden("Missing or invalid CSRF token. Reload the page and try again.")
    gov = users.get_governance(db)
    actor = Actor(
        kind="user",
        id=user.id,
        is_active_super_admin=users.is_active_super_admin(gov, user.id),
        ip=client_ip(request),
    )
    return Current(actor=actor, user=user, session=row)


CurrentDep = Annotated[Current, Depends(current)]
