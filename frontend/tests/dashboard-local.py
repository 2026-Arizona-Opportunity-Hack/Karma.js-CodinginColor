"""Create an isolated synthetic QA database and serve FastAPI. Never reads .env URLs.

Run from frontend: ../backend/.venv/Scripts/python.exe tests/dashboard-local.py
The database is deliberately retained for inspection; its unique name is printed.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[2]
backend = root / "backend"
database = "cic_33_" + uuid.uuid4().hex[:10]
# Local Docker defaults only. No environment or shared/hosted database accepted.
with psycopg.connect(
    host="127.0.0.1", port=5432, dbname="postgres", user="cic", password="cic",
    connect_timeout=3, autocommit=True,
) as conn:
    conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
url = f"postgresql+psycopg://cic:cic@127.0.0.1:5432/{database}"
os.environ.update(DATABASE_URL=url, TEST_DATABASE_URL=url, APP_ENV="test", COOKIE_SECURE="false", MESSAGING_MODE="dry_run")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, check=True)
sys.path.insert(0, str(backend))
from tests import seed  # noqa: E402

today = datetime.now(ZoneInfo("America/Phoenix")).date()
with Session(create_engine(url)) as db:
    owner = seed.add_user(db, "Synthetic Steward")
    inactive = seed.add_user(db, "Synthetic Former Steward", active=False)
    donor = seed.add_donor(db, "Synthetic Alex Rivera", owner=owner)
    db.execute(text("UPDATE donors SET created_at=:at WHERE id=:id"), {
        "at": datetime.combine(today - timedelta(days=100), datetime.min.time(), tzinfo=ZoneInfo("America/Phoenix")), "id": donor,
    })
    gift_donor = seed.add_donor(db, "Synthetic Desert Learning Collective", owner=owner)
    seed.add_gift(db, gift_donor, today - timedelta(days=3), 25000)
    step_donor = seed.add_donor(db, "Synthetic Maya Chen", owner=owner)
    seed.add_next_step(db, step_donor, owner, "Share the student showcase", today + timedelta(days=2))
    seed.add_donor(db, "Synthetic Sunrise Community Fund", owner=inactive)
    db.commit()
path = root / "frontend/.test-build/33-session.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"email": "synthetic.steward@example.org", "password": seed.PASSWORD}))
print(f"Isolated local database: {database}", flush=True)
os.chdir(backend)
import uvicorn  # noqa: E402

uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=8000, access_log=False)
