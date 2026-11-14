"""Operator commands (NFR-9). Run from backend/:

    uv run python -m app.cli setup [--file members.local.json]
    uv run python -m app.cli superadmin {create,activate,flatten,transfer,deactivate} [--email X]
    uv run python -m app.cli seed-demo | reset-demo        (only with DEMO_MODE=true)

`setup` prints each new member's initial password once. Nothing is written to disk.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import CLI
from app.clock import Clock, get_clock
from app.db.session import get_sessionmaker
from app.errors import AppError
from app.repos import audit, users
from app.security import generate_password, hash_password
from app.services.governance import superadmin
from app.settings import get_settings

DEMO_MEMBERS = [
    ("diana@demo.cic.test", "Diana (demo)"),
    ("marcus@demo.cic.test", "Marcus (demo)"),
    ("priya@demo.cic.test", "Priya (demo)"),
]


def _load_members(path: str | None) -> tuple[list[tuple[str, str]], str | None]:
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        members = [(m["email"], m["display_name"]) for m in data["members"]]
        return members, data.get("super_admin")
    print("Add board members. Leave email empty to finish.")
    members = []
    while email := input("  email: ").strip():
        members.append((email, input("  display name: ").strip() or email))
    sa = input("Super admin email (empty = flat hierarchy): ").strip() or None
    return members, sa


def add_members(db: Session, members: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Create members that do not exist yet. Returns (email, initial password) pairs."""
    created = []
    for email, name in members:
        if "@" not in email or users.find_by_email_for_login(db, email):
            print(f"  skip {email} (invalid or already exists)")
            continue
        password = generate_password()
        u = users.create(
            db, CLI, email=email, display_name=name, password_hash=hash_password(password)
        )
        audit.write(db, CLI, "user.create", entity="user", entity_id=u.id)
        created.append((email, password))
    return created


def cmd_setup(db: Session, clock: Clock, args: argparse.Namespace) -> None:
    members, sa = _load_members(args.file)
    created = add_members(db, members)
    if sa:
        superadmin.create(db, CLI, clock, sa)
    db.commit()
    print("\nInitial passwords (shown once; give each to its owner privately):")
    for email, password in created:
        print(f"  {email}  {password}")
    print(f"Super admin: {sa or 'none (flat hierarchy)'}")


def cmd_superadmin(db: Session, clock: Clock, args: argparse.Namespace) -> None:
    action = args.action
    if action in ("create", "transfer") and not args.email:
        raise SystemExit(f"superadmin {action} needs --email")
    if action == "create":
        superadmin.create(db, CLI, clock, args.email)
    elif action == "transfer":
        superadmin.transfer(db, CLI, clock, args.email)
    else:
        {"activate": superadmin.activate, "flatten": superadmin.flatten,
         "deactivate": superadmin.deactivate}[action](db, CLI, clock)  # fmt: skip
    db.commit()
    print(f"superadmin {action}: done")


def _require_demo() -> None:
    if not get_settings().demo_mode:
        raise SystemExit("Refusing: set DEMO_MODE=true to use demo commands.")


def cmd_seed_demo(db: Session, clock: Clock, args: argparse.Namespace) -> None:
    _require_demo()
    created = add_members(db, DEMO_MEMBERS)
    db.commit()
    for email, password in created:
        print(f"  {email}  {password}")


def cmd_reset_demo(db: Session, clock: Clock, args: argparse.Namespace) -> None:
    """Wipe every table and seed again. Demo deployments only."""
    _require_demo()
    tables = db.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
             "AND tablename <> 'alembic_version'")
    ).scalars()  # fmt: skip
    names = ", ".join(f'"{t}"' for t in tables)
    db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    db.execute(text("INSERT INTO governance (id) VALUES (1)"))
    audit.write(db, CLI, "demo.reset")
    cmd_seed_demo(db, clock, args)


COMMANDS: dict[str, Callable[[Session, Clock, argparse.Namespace], None]] = {
    "setup": cmd_setup,
    "superadmin": cmd_superadmin,
    "seed-demo": cmd_seed_demo,
    "reset-demo": cmd_reset_demo,
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="CIC Compass operator CLI")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup", help="create board members (and optionally the super admin)")
    s.add_argument("--file", help='JSON: {"members": [{"email", "display_name"}], "super_admin"}')
    sa = sub.add_parser("superadmin", help="manage the single super admin")
    sa.add_argument("action", choices=["create", "activate", "flatten", "transfer", "deactivate"])
    sa.add_argument("--email")
    sub.add_parser("seed-demo", help="add demo members (DEMO_MODE only)")
    sub.add_parser("reset-demo", help="wipe all data and seed demo members (DEMO_MODE only)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    db = get_sessionmaker()()
    try:
        COMMANDS[args.command](db, get_clock(), args)
    except AppError as e:
        db.rollback()
        print(f"error: {e.message}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
