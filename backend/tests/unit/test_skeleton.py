from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.clock import FixedClock, today
from app.main import create_app
from app.settings import Settings, get_settings


def test_healthz_is_public() -> None:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_plain_postgres_urls_use_psycopg_driver() -> None:
    s = Settings(database_url="postgres://u:p@h/db")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@h/db"
    s = Settings(database_url="postgresql://u:p@h/db?sslmode=require")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@h/db?sslmode=require"


def test_today_uses_phoenix_time() -> None:
    # 03:00 UTC on Nov 15 is still Nov 14 in Phoenix (UTC-7, no DST).
    clock = FixedClock(datetime(2026, 11, 15, 3, 0, tzinfo=UTC))
    assert today(clock).isoformat() == "2026-11-14"


def test_spa_fallback_and_api_404(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<p>app</p>")
    (tmp_path / "logo.svg").write_text("<svg/>")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/donors/12").text == "<p>app</p>"
        assert client.get("/logo.svg").text == "<svg/>"
        assert client.get("/api/app/nope").status_code == 404
        assert client.get("/../pyproject.toml").text == "<p>app</p>"
    finally:
        get_settings.cache_clear()
