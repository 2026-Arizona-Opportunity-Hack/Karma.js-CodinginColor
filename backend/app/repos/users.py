"""Users and governance. Auth lookups run before an Actor exists, so they take none;
everything that changes data takes the acting Actor."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import Governance, User


def find_by_email_for_login(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email.strip())).scalar_one_or_none()


def get_for_session(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_governance(db: Session) -> Governance:
    gov = db.get(Governance, 1)
    if gov is None:  # created by migration 0001; missing means a broken database
        raise RuntimeError("governance row missing")
    return gov


def is_active_super_admin(gov: Governance, user_id: int) -> bool:
    return gov.super_admin_state == "active" and gov.super_admin_user_id == user_id


def create(db: Session, actor: Actor, *, email: str, display_name: str, password_hash: str) -> User:
    # Only the setup CLI and invite acceptance create users; neither grants super admin.
    if actor.kind not in ("cli", "system"):
        raise PermissionError("users are created by the setup CLI or an invite")
    user = User(email=email.strip(), display_name=display_name.strip(), password_hash=password_hash)
    db.add(user)
    db.flush()
    return user


def set_password(db: Session, actor: Actor, user: User, password_hash: str) -> None:
    if actor.kind != "cli" and actor.user_id != user.id:
        raise PermissionError("only the user or the setup CLI can set a password")
    user.password_hash = password_hash


def set_active(db: Session, actor: Actor, user: User, active: bool, at: datetime) -> None:
    if actor.kind != "cli":
        raise PermissionError("in-app deactivation arrives in Phase 3 with policy checks")
    user.is_active = active
    user.deactivated_at = None if active else at
