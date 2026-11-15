"""/api/app/auth: login, logout, me."""

from fastapi import APIRouter, Request, Response

from app.errors import Invalid
from app.repos import users
from app.routes.deps import (
    CSRF_COOKIE,
    DB,
    SESSION_COOKIE,
    ClockDep,
    CurrentDep,
    client_ip,
)
from app.schemas.auth import GovernanceOut, LoginIn, MeOut
from app.services.auth import service
from app.settings import get_settings

router = APIRouter(prefix="/api/app/auth", tags=["app:auth"])


def _me(
    db: DB, user_id: int, email: str, name: str, *, is_super_admin: bool | None = None
) -> MeOut:
    gov = users.get_governance(db)
    return MeOut(
        id=user_id,
        email=email,
        display_name=name,
        is_super_admin=(
            users.is_active_super_admin(gov, user_id) if is_super_admin is None else is_super_admin
        ),
        governance=GovernanceOut(
            mode="super_admin" if gov.super_admin_state == "active" else "flat",
            reassign_scope=gov.reassign_scope,
        ),
    )


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB, clock: ClockDep) -> MeOut:
    result = service.login(
        db,
        clock,
        email=body.email,
        password=body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    settings = get_settings()
    max_age = settings.session_absolute_days * 86400
    secure = settings.cookie_secure
    response.set_cookie(
        SESSION_COOKIE, result.session_token, max_age=max_age, httponly=True,
        secure=secure, samesite="lax", path="/",
    )  # fmt: skip
    # Readable by the SPA so it can echo it in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE, result.csrf_token, max_age=max_age, httponly=False,
        secure=secure, samesite="lax", path="/",
    )  # fmt: skip
    u = result.user
    return _me(db, u.id, u.email, u.display_name)


@router.post("/logout", status_code=204)
def logout(cur: CurrentDep, response: Response, db: DB, clock: ClockDep) -> Response:
    if cur.session is None:
        raise Invalid("An API key has no session to log out of; revoke the key instead.")
    service.logout(db, clock, cur.session, cur.actor)
    response.status_code = 204
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


@router.get("/me")
def me(cur: CurrentDep, db: DB) -> MeOut:
    return _me(
        db, cur.user.id, cur.user.email, cur.user.display_name,
        is_super_admin=cur.actor.is_active_super_admin,
    )  # fmt: skip
