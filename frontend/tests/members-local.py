"""Serve a fresh synthetic members QA database on local Docker PostgreSQL only.

Run from frontend: ../backend/.venv/Scripts/python.exe tests/members-local.py
Never loads .env connection strings; leaves the uniquely named database for inspection.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[2]
backend = root / "backend"
database = "cic_35_" + uuid.uuid4().hex[:10]
with psycopg.connect(host="127.0.0.1", port=5432, dbname="postgres", user="cic", password="cic", connect_timeout=3, autocommit=True) as conn:
    conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
url = f"postgresql+psycopg://cic:cic@127.0.0.1:5432/{database}"
os.environ.update(DATABASE_URL=url, TEST_DATABASE_URL=url, APP_ENV="test", COOKIE_SECURE="false", MESSAGING_MODE="dry_run")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, check=True)
sys.path.insert(0, str(backend))
from tests import seed
from app.authz.actor import CLI
from app.clock import SystemClock
from app.services.governance import superadmin

with Session(create_engine(url)) as db:
    admin = seed.add_user(db, "Synthetic Board Lead")
    steward = seed.add_user(db, "Synthetic Avery Morgan")
    seed.add_user(db, "Synthetic Former Steward", active=False)
    seed.add_donor(db, "Synthetic Learning Partners", owner=steward, email="partners@example.test")
    seed.add_donor(db, "Synthetic Community Fund", owner=steward)
    superadmin.create(db, CLI, SystemClock(), "synthetic.board.lead@example.org")
    db.commit()
path = root / "frontend/.test-build/35-session.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"email": "synthetic.board.lead@example.org", "password": seed.PASSWORD, "peer_email": "synthetic.avery.morgan@example.org", "peer_id": steward, "admin_id": admin, "database": database}))
print(f"Isolated local database: {database}", flush=True)
os.chdir(backend)
import uvicorn

uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=8000, access_log=False)
