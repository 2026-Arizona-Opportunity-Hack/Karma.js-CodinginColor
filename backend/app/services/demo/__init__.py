"""Demo data for DEMO_MODE deployments (NFR-9). Synthetic fixtures only, loaded through the real
importer so the demo exercises ownership, dedupe, reviews and reminders exactly like live data."""

import json
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.db.models import Donor
from app.errors import Conflict
from app.schemas.common import ImportSource
from app.services.ingest import batches, service

SOURCES: tuple[ImportSource, ...] = ("spreadsheet", "zeffy", "benevity", "generic")
_HERE = Path(__file__).resolve()
# Repo root while developing; /app in the Docker image (the Dockerfile copies fixtures/ there).
CANDIDATES = (_HERE.parents[4] / "fixtures", _HERE.parents[3] / "fixtures")


def fixtures_dir() -> Path:
    for path in CANDIDATES:
        if (path / "manifest.json").is_file():
            return path
    raise Conflict("The synthetic fixtures folder was not found next to the app.")


def load_fixtures(db: Session, clock: Clock, uploader_id: int) -> list[tuple[str, int, int]]:
    """Import the four synthetic files in manifest order as `uploader_id`. Returns
    (filename, donors created, gifts added). Refuses to run on a database that has donors."""
    if db.scalar(select(func.count()).select_from(Donor)):
        raise Conflict("The database already has donors. Run reset-demo to start over.")
    root = fixtures_dir()
    order: list[str] = json.loads((root / "manifest.json").read_text(encoding="utf-8"))[
        "import_order"
    ]
    actor = Actor(kind="user", id=uploader_id)
    loaded = []
    for source, filename in zip(SOURCES, order, strict=True):
        data = (root / filename).read_bytes()
        shown = service.preview(db, actor, clock, source, filename, data)
        saved = batches.commit(db, actor, clock, shown.batch.id)
        summary = saved.summary or shown.summary
        loaded.append((filename, summary.new_donors, summary.gift_count))
    return loaded


def restore_reference_data(db: Session) -> None:
    """Rows the migrations create. A wipe removes them, and imports need the programs."""
    db.execute(text("INSERT INTO governance (id) VALUES (1) ON CONFLICT DO NOTHING"))
    db.execute(
        text(
            "INSERT INTO app_settings (key, value) VALUES ('thank_you_days_first','2'),"
            "('thank_you_days_repeat','7'),('quarterly_days','90'),('import_cutoff_days','60'),"
            "('retention_basis','\"rolling\"') ON CONFLICT DO NOTHING"
        )
    )
    db.execute(
        text(
            "INSERT INTO programs (name, slug) VALUES ('AI Academy','ai-academy'),"
            "('K12 Program','k12-program'),('Summer Camp','summer-camp'),"
            "('Day of Compute','day-of-compute'),('General','general') ON CONFLICT DO NOTHING"
        )
    )
