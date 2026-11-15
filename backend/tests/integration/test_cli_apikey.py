"""python -m app.cli apikey {create,list,revoke}: the break-glass route to API keys."""

import hashlib
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import main
from app.db.models import ApiKey, AuditLog
from app.main import create_app
from tests import seed

KEY_RE = re.compile(r"cic_live_[A-Za-z0-9_-]{43}")


@pytest.fixture
def diana(db: Session) -> int:
    uid = seed.add_user(db, "Diana")
    db.commit()
    return uid


def create(capsys, name: str = "Dashboard", email: str = "diana@example.org") -> str:
    assert main(["apikey", "create", "--name", name, "--email", email]) == 0
    out = capsys.readouterr().out
    found = KEY_RE.findall(out)
    assert len(found) == 1, out
    return found[0]


def call(key: str, path: str = "/api/v1/totals/by-program") -> int:
    return (
        TestClient(create_app()).get(path, headers={"Authorization": f"Bearer {key}"}).status_code
    )


def test_create_prints_the_key_once_and_it_works(db: Session, diana, capsys) -> None:
    key = create(capsys)
    row = db.execute(select(ApiKey)).scalar_one()
    assert row.key_hash == hashlib.sha256(key.encode()).hexdigest()  # only the hash is stored
    assert (row.name, row.created_by, row.scopes, row.prefix) == (
        "Dashboard", diana, ["read:aggregates"], key[:13],
    )  # fmt: skip
    assert call(key) == 200
    main(["apikey", "list"])
    assert key not in capsys.readouterr().out  # never shown again


def test_create_is_audited_as_cli_without_the_key(db: Session, diana, capsys) -> None:
    key = create(capsys)
    entry = db.execute(select(AuditLog).where(AuditLog.action == "apikey.create")).scalar_one()
    assert entry.actor_kind == "cli" and entry.entity == "api_key"
    assert key not in str(entry.data) and entry.data == {"name": "Dashboard"}


def test_list_shows_prefix_last_used_and_status(db: Session, diana, capsys) -> None:
    main(["apikey", "list"])
    assert "No API keys yet." in capsys.readouterr().out
    first = create(capsys, "Dashboard")
    create(capsys, "Spreadsheet")
    call(first)
    assert main(["apikey", "revoke", "2"]) == 0
    capsys.readouterr()
    main(["apikey", "list"])
    lines = capsys.readouterr().out.splitlines()
    assert any("Dashboard" in ln and first[:13] in ln and "active" in ln for ln in lines)
    assert any("Spreadsheet" in ln and "revoked" in ln and "never" in ln for ln in lines)
    assert not any(first in ln for ln in lines)


def test_revoke_stops_the_key_at_once_and_is_audited(db: Session, diana, capsys) -> None:
    key = create(capsys)
    assert call(key) == 200
    assert main(["apikey", "revoke", "1"]) == 0
    assert "Revoked key 1 (Dashboard)" in capsys.readouterr().out
    assert call(key) == 401
    entry = db.execute(select(AuditLog).where(AuditLog.action == "apikey.revoke")).scalar_one()
    assert entry.actor_kind == "cli" and entry.entity_id == 1


def test_revoke_unknown_key_fails_cleanly(db: Session, diana, capsys) -> None:
    assert main(["apikey", "revoke", "99"]) == 1
    assert "API key not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv,message",
    [
        (["apikey", "create"], "needs --name and --email"),
        (["apikey", "create", "--name", "x"], "needs --name and --email"),
        (["apikey", "create", "--name", "x", "--email", "ghost@example.org"], "No active board"),
        (["apikey", "revoke"], "needs the key id"),
    ],
)
def test_bad_usage_stops_with_a_message(db: Session, diana, argv, message) -> None:
    with pytest.raises(SystemExit) as stop:
        main(argv)
    assert message in str(stop.value)
    assert db.execute(select(ApiKey)).first() is None


def test_deactivated_member_cannot_own_a_key(db: Session, diana) -> None:
    db.execute(ApiKey.__table__.metadata.tables["users"].update().values(is_active=False))
    db.commit()
    with pytest.raises(SystemExit):
        main(["apikey", "create", "--name", "x", "--email", "diana@example.org"])
    assert db.execute(select(ApiKey)).first() is None


def test_email_match_ignores_case(db: Session, diana, capsys) -> None:
    create(capsys, email="  DIANA@Example.org ")
    assert db.execute(select(ApiKey.created_by)).scalar_one() == diana
