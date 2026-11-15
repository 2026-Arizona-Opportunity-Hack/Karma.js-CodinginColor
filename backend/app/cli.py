"""Operator commands (NFR-9). Run from backend/:

    uv run python -m app.cli setup [--file members.local.json]
    uv run python -m app.cli superadmin {create,activate,flatten,transfer,deactivate} [--email X]
    uv run python -m app.cli seed-demo [--members-only] | reset-demo   (only with DEMO_MODE=true)

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
from app.repos import apikeys, audit, users
from app.security import generate_password, hash_password
from app.services import demo
from app.services.apikeys import service as apikey_service
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


def cmd_apikey(db: Session, clock: Clock, args: argparse.Namespace) -> None:
    """Create, list or revoke public API keys (API-1). The break-glass route until the app has a
    settings page; every change is audited like the in-app one."""
    if args.action == "list":
        rows = apikeys.list_all(db, CLI)
        print(f"{'id':>3}  {'name':<24} {'prefix':<14} {'last used':<20} status")
        for k in rows:
            used = k.last_used_at.strftime("%Y-%m-%d %H:%M") if k.last_used_at else "never"
            print(f"{k.id:>3}  {k.name:<24} {k.prefix:<14} {used:<20} "
                  f"{'revoked' if k.revoked_at else 'active'}")  # fmt: skip
        if not rows:
            print("No API keys yet.")
        return
    if args.action == "revoke":
        if args.key_id is None:
            raise SystemExit("apikey revoke needs the key id (see: apikey list)")
        row = apikey_service.revoke(db, clock, CLI, args.key_id)
        db.commit()
        print(f"Revoked key {row.id} ({row.name}); it stops working immediately.")
        return
    if not args.name or not args.email:
        raise SystemExit("apikey create needs --name and --email (the member it is recorded for)")
    member = users.find_by_email_for_login(db, args.email.strip().lower())
    if member is None or not member.is_active:
        raise SystemExit(f"No active board member with email {args.email}")
    made = apikey_service.create(
        db, CLI, name=args.name.strip(), scopes=[apikey_service.SCOPE_AGGREGATES],
        created_by=member.id,
    )  # fmt: skip
    db.commit()
    print()
    print(f"API key {made.row.id} ({made.row.name}), scope read:aggregates.")
    print("Shown once; it cannot be recovered. Store it in a password manager:")
    print()
    print(f"  {made.key}")
    print()


def _require_demo() -> None:
    if not get_settings().demo_mode:
        raise SystemExit("Refusing: set DEMO_MODE=true to use demo commands.")


def cmd_seed_demo(db: Session, clock: Clock, args: argparse.Namespace) -> None:
    """Demo members, then the synthetic fixtures through the real importer (NFR-9)."""
    _require_demo()
    created = add_members(db, DEMO_MEMBERS)
    db.commit()
    for email, password in created:
        print(f"  {email}  {password}")
    if getattr(args, "members_only", False):
        return
    first = users.find_by_email_for_login(db, DEMO_MEMBERS[0][0])
    if first is None:
        raise SystemExit("Demo members are missing; run reset-demo.")
    for filename, donors, gifts in demo.load_fixtures(db, clock, first.id):
        print(f"  imported {filename}: {donors} new donors, {gifts} gifts")
    db.commit()


def cmd_reset_demo(db: Session, clock: Clock, args: argparse.Namespace) -> None:
    """Wipe every table and seed again. Demo deployments only."""
    _require_demo()
    tables = db.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
             "AND tablename <> 'alembic_version'")
    ).scalars()  # fmt: skip
    names = ", ".join(f'"{t}"' for t in tables)
    db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    demo.restore_reference_data(db)
    audit.write(db, CLI, "demo.reset")
    cmd_seed_demo(db, clock, args)


COMMANDS: dict[str, Callable[[Session, Clock, argparse.Namespace], None]] = {
    "setup": cmd_setup,
    "superadmin": cmd_superadmin,
    "apikey": cmd_apikey,
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
    ak = sub.add_parser("apikey", help="create, list or revoke public API keys")
    ak.add_argument("action", choices=["create", "list", "revoke"])
    ak.add_argument("key_id", nargs="?", type=int, help="for revoke: the key id")
    ak.add_argument("--name", help="for create: what the key is for, e.g. Dashboard")
    ak.add_argument("--email", help="for create: the board member the key is recorded for")
    sd = sub.add_parser("seed-demo", help="add demo members and synthetic data (DEMO_MODE only)")
    sd.add_argument("--members-only", action="store_true", help="skip the synthetic data import")
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
