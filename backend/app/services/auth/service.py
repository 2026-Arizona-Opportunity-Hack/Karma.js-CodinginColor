"""Login, logout and session resolution (AUTH-1, AUTH-2, AUTH-5, AUTH-6, AUTH-7)."""

import hmac
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.db.models import SessionRow, User
from app.errors import TooManyRequests, Unauthorized
from app.repos import audit, sessions, users
from app.security import new_token, sha256_hex, verify_password
from app.settings import get_settings

MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_FAILED = "Email or password is incorrect."


@dataclass(frozen=True)
class LoginResult:
    user: User
    session_token: str
    csrf_token: str


def login(
    db: Session, clock: Clock, *, email: str, password: str, ip: str | None, user_agent: str | None
) -> LoginResult:
    now = clock.now()
    email = email.strip().lower()
    anon = Actor(kind="system", id=None, ip=ip)
    if audit.count_failed_logins(db, email=email, ip=ip, since=now - FAILURE_WINDOW) >= (
        MAX_FAILURES
    ):
        raise TooManyRequests("Too many attempts. Try again in 15 minutes.")

    user = users.find_by_email_for_login(db, email)
    ok = verify_password(user.password_hash if user else None, password)
    if user is None or not ok or not user.is_active:
        # Same message for unknown email, wrong password and deactivated account.
        audit.write(db, anon, "auth.login_failed", data={"email": email}, at=now)
        db.commit()  # keep the failure even though the request errors
        raise Unauthorized(LOGIN_FAILED)

    settings = get_settings()
    token, csrf = new_token(), new_token()
    expires = now + timedelta(days=settings.session_absolute_days)
    sessions.create(
        db,
        user_id=user.id,
        token_hash=sha256_hex(token),
        csrf_hash=sha256_hex(csrf),
        now=now,
        expires_at=expires,
        ip=ip,
        user_agent=user_agent,
    )
    audit.write(
        db, Actor(kind="user", id=user.id, ip=ip), "auth.login", entity="user", entity_id=user.id
    )
    return LoginResult(user=user, session_token=token, csrf_token=csrf)


def resolve(db: Session, clock: Clock, token: str | None) -> tuple[SessionRow, User] | None:
    """The live session and its active user, or None. Slides the idle window."""
    if not token:
        return None
    row = sessions.find_live(db, sha256_hex(token))
    if row is None:
        return None
    now = clock.now()
    idle = timedelta(hours=get_settings().session_idle_hours)
    user = users.get_for_session(db, row.user_id)
    if now >= row.expires_at or now >= row.last_seen_at + idle or user is None:
        return None
    if not user.is_active:  # AUTH-7: deactivated users lose access at once
        sessions.revoke_all_for_user(db, user.id, now)
        return None
    row.last_seen_at = now
    return row, user


def csrf_ok(row: SessionRow, header_value: str | None, cookie_value: str | None) -> bool:
    """Double submit: header equals cookie, and both match the hash stored for this session."""
    if not header_value or not cookie_value:
        return False
    if not hmac.compare_digest(header_value, cookie_value):
        return False
    return hmac.compare_digest(sha256_hex(header_value), row.csrf_hash)


def logout(db: Session, clock: Clock, row: SessionRow, actor: Actor) -> None:
    sessions.revoke(db, row, clock.now())
    audit.write(db, actor, "auth.logout", entity="user", entity_id=actor.id)
