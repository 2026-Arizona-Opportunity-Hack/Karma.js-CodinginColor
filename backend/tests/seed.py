"""Direct inserts into the local test database (never a shared one) for report and API tests."""

import itertools
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.security import hash_password, sha256_hex

_n = itertools.count(1)


def _one(db: Session, sql: str, **p: Any) -> int:
    return int(db.execute(text(sql), p).scalar_one())


def add_user(db: Session, name: str, *, active: bool = True) -> int:
    return _one(
        db,
        "INSERT INTO users (email, display_name, password_hash, is_active) "
        "VALUES (:e, :n, :h, :a) RETURNING id",
        e=f"{name.lower().replace(' ', '.')}@example.org",
        n=name,
        h=hash_password("correct horse battery"),
        a=active,
    )


def add_donor(
    db: Session,
    name: str,
    *,
    owner: int | None = None,
    email: str | None = None,
    phone: str | None = None,
    notes: str | None = None,
    kind: str = "person",
    deleted: bool = False,
) -> int:
    return _one(
        db,
        "INSERT INTO donors (kind, display_name, email, phone, notes, owner_user_id, created_via, "
        "deleted_at) VALUES (:k, :n, :e, :p, :no, :o, 'manual', "
        "CASE WHEN :d THEN now() ELSE NULL END) RETURNING id",
        k=kind, n=name, e=email, p=phone, no=notes, o=owner, d=deleted,
    )  # fmt: skip


def add_gift(
    db: Session,
    donor: int | None,
    when: date,
    cents: int,
    *,
    program: str = "General",
    fee: int = 0,
    attribution: str | None = None,
    source: str = "manual",
    deleted: bool = False,
) -> int:
    attribution = attribution or ("linked" if donor is not None else "anonymous")
    return _one(
        db,
        "INSERT INTO gifts (donor_id, attribution, source, row_key, gift_date, gross_cents, "
        "fee_cents, net_cents, program_id, deleted_at) "
        "VALUES (:d, :a, :s, :k, :w, :g, :f, :g - :f, (SELECT id FROM programs WHERE name = :p), "
        "CASE WHEN :x THEN now() ELSE NULL END) RETURNING id",
        d=donor, a=attribution, s=source, k=f"test-{next(_n)}", w=when, g=cents, f=fee,
        p=program, x=deleted,
    )  # fmt: skip


def add_interaction(
    db: Session, donor: int, user: int | None, when: date, kind: str = "call"
) -> int:
    return _one(
        db,
        "INSERT INTO interactions (donor_id, user_id, kind, occurred_on, summary) "
        "VALUES (:d, :u, :k, :w, 'x') RETURNING id",
        d=donor, u=user, k=kind, w=when,
    )  # fmt: skip


def add_sent_message(db: Session, donor: int, user: int, at: datetime) -> int:
    return _one(
        db,
        "INSERT INTO messages (donor_id, kind, channel, status, subject, body, created_by, "
        "approved_by, approved_at, body_sha256_at_approval, sent_by, sent_at, delivery_mode) "
        "VALUES (:d, 'quarterly_update', 'email', 'sent', 's', 'b', :u, :u, :t, 'h', :u, :t, "
        "'dry_run') RETURNING id",
        d=donor, u=user, t=at,
    )  # fmt: skip


def add_api_key(db: Session, created_by: int, *, scopes: str = "read:aggregates") -> str:
    """Insert a key row directly and return the full key (only its hash is stored)."""
    key = f"cic_live_{next(_n):043d}"
    db.execute(
        text(
            "INSERT INTO api_keys (name, prefix, key_hash, scopes, created_by) "
            "VALUES ('test', :p, :h, ARRAY[:s], :u)"
        ),
        {"p": key[:13], "h": sha256_hex(key), "s": scopes, "u": created_by},
    )
    return key
