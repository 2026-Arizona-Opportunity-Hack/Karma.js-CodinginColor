import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import main
from app.db.models import AuditLog, Governance, User
from app.security import verify_password
from app.settings import get_settings


def gov(db: Session) -> tuple[str | None, str, str]:
    db.expire_all()
    g = db.get(Governance, 1)
    assert g is not None
    email = db.get(User, g.super_admin_user_id).email if g.super_admin_user_id else None
    return email, g.super_admin_state, g.reassign_scope


def actions(db: Session) -> list[str]:
    return list(db.execute(select(AuditLog.action).order_by(AuditLog.id)).scalars())


@pytest.fixture
def members_file(tmp_path: Path) -> str:
    p = tmp_path / "members.local.json"
    p.write_text(
        json.dumps(
            {
                "members": [
                    {"email": "diana@example.org", "display_name": "Diana"},
                    {"email": "sam@example.org", "display_name": "Sam"},
                ],
                "super_admin": "diana@example.org",
            }
        )
    )
    return str(p)


def test_setup_creates_members_with_printed_passwords(db: Session, members_file, capsys) -> None:
    assert main(["setup", "--file", members_file]) == 0
    out = capsys.readouterr().out
    diana = db.execute(select(User).where(User.email == "diana@example.org")).scalar_one()
    password = next(line.split()[1] for line in out.splitlines() if "diana@" in line)
    assert verify_password(diana.password_hash, password)
    assert password not in diana.password_hash
    assert gov(db) == ("diana@example.org", "active", "anyone")
    assert actions(db) == ["user.create", "user.create", "gov.super_admin_create"]


def test_setup_is_idempotent(db: Session, members_file) -> None:
    main(["setup", "--file", members_file])
    assert main(["setup", "--file", members_file]) == 1  # super admin already exists
    assert db.execute(select(User)).scalars().all().__len__() == 2


def test_superadmin_lifecycle_is_audited(db: Session, members_file) -> None:
    main(["setup", "--file", members_file])
    db.execute(Governance.__table__.update().values(reassign_scope="own_only"))
    db.commit()

    assert main(["superadmin", "flatten"]) == 0
    assert gov(db) == ("diana@example.org", "dormant", "anyone")
    assert main(["superadmin", "flatten"]) == 1  # already flat
    assert main(["superadmin", "activate"]) == 0
    assert gov(db)[1] == "active"
    assert main(["superadmin", "transfer", "--email", "sam@example.org"]) == 0
    assert gov(db) == ("sam@example.org", "active", "anyone")
    assert main(["superadmin", "deactivate"]) == 0
    sam = db.execute(select(User).where(User.email == "sam@example.org")).scalar_one()
    assert sam.is_active is False  # blocked, never deleted
    assert gov(db) == ("sam@example.org", "dormant", "anyone")
    assert main(["superadmin", "activate"]) == 1  # deactivated holder cannot be re-activated
    assert actions(db)[-4:] == [
        "gov.flatten",
        "gov.super_admin_activate",
        "gov.super_admin_transfer",
        "gov.super_admin_deactivate",
    ]
    assert all(a.actor_kind == "cli" for a in db.execute(select(AuditLog)).scalars())


def test_create_needs_existing_member(db: Session) -> None:
    assert main(["superadmin", "create", "--email", "ghost@example.org"]) == 1
    assert gov(db) == (None, "none", "anyone")


def test_demo_commands_refuse_without_demo_mode(db: Session, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    with pytest.raises(SystemExit):
        main(["reset-demo"])
    get_settings.cache_clear()


def test_reset_demo_wipes_and_seeds(db: Session, members_file, monkeypatch) -> None:
    main(["setup", "--file", members_file])
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        assert main(["reset-demo"]) == 0
    finally:
        get_settings.cache_clear()
    emails = set(db.execute(select(User.email)).scalars())
    assert "demo.reset" in actions(db)
    assert emails == {"diana@demo.cic.test", "marcus@demo.cic.test", "priya@demo.cic.test"}
    assert gov(db) == (None, "none", "anyone")
