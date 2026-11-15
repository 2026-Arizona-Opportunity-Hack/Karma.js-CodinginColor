"""Test database: a separate `cic_test` database, migrated once, truncated per test."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, make_url, text
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parent.parent
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://cic:cic@localhost:5432/cic_test"
)
# Set before any app module reads settings.
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["APP_ENV"] = "test"
os.environ["COOKIE_SECURE"] = "false"
os.environ["STATIC_DIR"] = str(BACKEND / "no-static-in-tests")


def alembic_config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def _cheap_password_hashing() -> None:
    """Tests log in constantly, and production-strength Argon2 costs about 50 ms per login.
    Use the cheapest Argon2id setting here; the app itself keeps its default strength."""
    from argon2 import PasswordHasher

    from app import security

    security._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    security._DUMMY_HASH = security._hasher.hash("not-a-real-password")


def _ensure_database() -> None:
    url = make_url(TEST_DB_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def migrated() -> None:
    _ensure_database()
    command.upgrade(alembic_config(), "head")


def _quote(table: str) -> str:
    return '"' + table + '"'


def _dirty_tables(conn: Connection) -> list[str]:
    """Tables that hold rows or whose id counter has moved. Truncating all ~25 tables costs
    about 260 ms; truncating only the few a test touched costs a fraction of that."""
    tables = list(
        conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        ).scalars()
    )
    if not tables:
        return []
    # Table names come from pg_tables, never from input.
    probes = (f"SELECT '{t}' WHERE EXISTS (SELECT 1 FROM {_quote(t)})" for t in tables)  # noqa: S608
    has_rows = " UNION ALL ".join(probes)
    dirty = set(conn.execute(text(has_rows)).scalars())
    moved = conn.execute(
        text("SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' "
             "AND last_value IS NOT NULL")
    ).scalars()  # fmt: skip
    dirty |= {s.removesuffix("_id_seq") for s in moved} & set(tables)
    return sorted(dirty)


def _truncate_all(conn: Connection) -> None:
    names = ", ".join(f'"{t}"' for t in _dirty_tables(conn))
    if names:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    # Rows created by migrations (reference data) come back after every wipe.
    conn.execute(text("INSERT INTO governance (id) VALUES (1) ON CONFLICT DO NOTHING"))
    conn.execute(
        text(
            "INSERT INTO app_settings (key, value) VALUES ('thank_you_days_first','2'),"
            "('thank_you_days_repeat','7'),('quarterly_days','90'),('import_cutoff_days','60'),"
            "('retention_basis','\"rolling\"')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO programs (name, slug) VALUES ('AI Academy','ai-academy'),"
            "('K12 Program','k12-program'),('Summer Camp','summer-camp'),"
            "('Day of Compute','day-of-compute'),('General','general')"
        )
    )
    _reseed_fields(conn)


@pytest.fixture
def db(migrated: None) -> Iterator[Session]:
    """A session on a clean database. Commits are real. The wipe happens before each test, not
    after it, so the next test pays for it once instead of twice."""
    from app.db.session import get_engine, get_sessionmaker

    with get_engine().begin() as conn:
        _truncate_all(conn)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _reseed_fields(conn: Connection) -> None:
    """The built-in field definitions come from migration 0006 and return after every wipe."""
    import importlib.util

    path = BACKEND / "alembic" / "versions" / "0006_field_definitions.py"
    spec = importlib.util.spec_from_file_location("migration_0006", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    order: dict[str, int] = {}
    for entity, key, label, ftype, choices, required, contact, listed in mod.BUILTINS:
        order[entity] = order.get(entity, 0) + 10
        conn.execute(
            text(
                "INSERT INTO field_definitions (entity, key, label, type, choices, is_builtin,"
                " is_required, is_contact, show_in_list, position) VALUES (:e, :k, :l, :t, :c,"
                " true, :r, :ct, :s, :p)"
            ),
            dict(e=entity, k=key, l=label, t=ftype, c=choices, r=required, ct=contact,
                 s=listed, p=order[entity]),
        )  # fmt: skip
