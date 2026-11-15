"""seed-demo and reset-demo (NFR-9): synthetic data through the real importer, DEMO_MODE only."""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import main
from app.db.models import AuditLog, Donor, Gift, ImportBatch, User
from app.settings import get_settings

MANIFEST = json.loads(
    (Path(__file__).resolve().parents[3] / "fixtures" / "manifest.json").read_text(encoding="utf-8")
)


@pytest.fixture
def demo_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def n(db: Session, model) -> int:
    total = db.scalar(select(func.count()).select_from(model)) or 0
    db.rollback()  # end the read transaction: reset-demo's TRUNCATE would wait on it
    return total


def test_seed_demo_imports_the_four_synthetic_files_in_manifest_order(
    db: Session, demo_mode, capsys
) -> None:
    assert main(["seed-demo"]) == 0
    out = capsys.readouterr().out
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.id)).all()
    assert sorted(b.filename for b in batches) == sorted(MANIFEST["import_order"])
    assert {b.status for b in batches} == {"committed"}
    assert n(db, User) == 3 and n(db, Donor) > 100 and n(db, Gift) > 400
    assert "synthetic_zeffy_like.csv" in out and "@demo.cic.test" in out
    # Every donor got an owner through the normal round-robin (OWN-2).
    assert (
        db.scalar(select(func.count()).select_from(Donor).where(Donor.owner_user_id.is_(None))) == 0
    )
    assert n(db, AuditLog) > 4


def test_seed_demo_refuses_without_demo_mode_and_writes_nothing(db: Session, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit, match="DEMO_MODE"):
            main(["seed-demo"])
        with pytest.raises(SystemExit, match="DEMO_MODE"):
            main(["reset-demo"])
    finally:
        get_settings.cache_clear()
    assert n(db, User) == 0 and n(db, Donor) == 0


def test_seeding_twice_is_refused_and_changes_nothing(db: Session, demo_mode, capsys) -> None:
    assert main(["seed-demo"]) == 0
    donors, gifts = n(db, Donor), n(db, Gift)
    assert main(["seed-demo"]) == 1  # donors already exist
    assert "reset-demo" in capsys.readouterr().err
    assert (n(db, Donor), n(db, Gift)) == (donors, gifts)


def test_reset_demo_wipes_everything_and_seeds_the_same_data_again(db: Session, demo_mode) -> None:
    main(["seed-demo"])
    donors, gifts = n(db, Donor), n(db, Gift)
    assert main(["reset-demo"]) == 0
    assert (n(db, Donor), n(db, Gift), n(db, User)) == (donors, gifts, 3)
    assert (
        db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "demo.reset"))
        == 1
    )


def test_members_only_skips_the_data_import(db: Session, demo_mode) -> None:
    assert main(["seed-demo", "--members-only"]) == 0
    assert (n(db, User), n(db, Donor), n(db, ImportBatch)) == (3, 0, 0)
