import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Governance, User
from app.db.session import get_engine
from tests.conftest import alembic_config


def _user(db: Session, email: str = "a@example.org") -> User:
    u = User(email=email, display_name="A", password_hash="x")
    db.add(u)
    db.flush()
    return u


def test_migrations_downgrade_and_reapply(migrated: None) -> None:
    get_engine().dispose()
    command.downgrade(alembic_config(), "base")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.users')")).scalar() is None
    command.upgrade(alembic_config(), "head")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM governance")).scalar() == 1


def test_governance_starts_flat(db: Session) -> None:
    gov = db.get(Governance, 1)
    assert gov is not None
    assert (gov.super_admin_user_id, gov.super_admin_state, gov.reassign_scope) == (
        None,
        "none",
        "anyone",
    )


def test_governance_is_a_single_row(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO governance (id) VALUES (2)"))


def test_state_must_match_super_admin_user(db: Session) -> None:
    gov = db.get(Governance, 1)
    assert gov is not None
    gov.super_admin_state = "active"  # no user set
    with pytest.raises(IntegrityError):
        db.flush()


def test_own_only_scope_needs_active_super_admin(db: Session) -> None:
    u = _user(db)
    gov = db.get(Governance, 1)
    assert gov is not None
    gov.super_admin_user_id, gov.super_admin_state, gov.reassign_scope = u.id, "active", "own_only"
    db.flush()  # allowed while active
    gov.super_admin_state = "dormant"
    with pytest.raises(IntegrityError):
        db.flush()


def test_user_email_is_case_insensitive_unique(db: Session) -> None:
    _user(db, "Diana@Example.org")
    with pytest.raises(IntegrityError):
        _user(db, "diana@example.org")


def test_super_admin_user_cannot_be_deleted(db: Session) -> None:
    u = _user(db)
    db.execute(
        text(
            "UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
            "WHERE id = 1"
        ),
        {"u": u.id},
    )
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM users WHERE id = :u"), {"u": u.id})
