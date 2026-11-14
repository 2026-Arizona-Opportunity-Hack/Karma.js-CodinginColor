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


def _truncate_all(conn: Connection) -> None:
    tables = conn.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename <> 'alembic_version'"
        )
    ).scalars()
    names = ", ".join(f'"{t}"' for t in tables)
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


@pytest.fixture
def db(migrated: None) -> Iterator[Session]:
    """A session on a clean database. Commits are real; tables are wiped afterwards."""
    from app.db.session import get_engine, get_sessionmaker

    with get_engine().begin() as conn:
        _truncate_all(conn)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
        with get_engine().begin() as conn:
            _truncate_all(conn)
