from datetime import date

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Donor,
    DonorIdentity,
    Gift,
    ImportBatch,
    Program,
    SourceProgramMap,
    User,
)
from app.db.session import get_engine
from tests.conftest import alembic_config


def program(db: Session, name: str = "General") -> Program:
    return db.execute(select(Program).where(Program.name == name)).scalar_one()


def donor(db: Session, name: str = "Ada Lovelace", **kw) -> Donor:
    d = Donor(**({"kind": "person", "display_name": name, "created_via": "manual"} | kw))
    db.add(d)
    db.flush()
    return d


def gift(db: Session, d: Donor | None, key: str = "k1", **kw) -> Gift:
    values = {
        "attribution": "linked" if d else "anonymous",
        "donor_id": d.id if d else None,
        "source": "manual",
        "row_key": key,
        "gift_date": date(2026, 10, 1),
        "gross_cents": 5000,
        "fee_cents": 0,
        "net_cents": 5000,
        "program_id": program(db).id,
    } | kw
    g = Gift(**values)
    db.add(g)
    db.flush()
    return g


def test_programs_are_seeded(db: Session) -> None:
    names = set(db.execute(select(Program.name)).scalars())
    assert names == {"AI Academy", "K12 Program", "Summer Camp", "Day of Compute", "General"}


def test_downgrade_to_previous_revision_and_back(migrated: None) -> None:
    get_engine().dispose()
    command.downgrade(alembic_config(), "0001")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.gifts')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.users')")).scalar() is not None
    command.upgrade(alembic_config(), "head")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM programs")).scalar() == 5


@pytest.mark.parametrize("field,value", [("kind", "alien"), ("created_via", "magic")])
def test_donor_enums_are_checked(db: Session, field: str, value: str) -> None:
    with pytest.raises(IntegrityError):
        donor(db, **{field: value})


def test_donor_cannot_be_merged_into_itself(db: Session) -> None:
    d = donor(db)
    d.merged_into_id = d.id
    with pytest.raises(IntegrityError):
        db.flush()


def test_strong_identity_is_unique_but_name_org_repeats(db: Session) -> None:
    a, b = donor(db, "A"), donor(db, "B")
    db.add_all(
        [
            DonorIdentity(donor_id=a.id, kind="name_org", value_norm="jo smith", source="s"),
            DonorIdentity(donor_id=b.id, kind="name_org", value_norm="jo smith", source="s"),
            DonorIdentity(donor_id=a.id, kind="email", value_norm="a@example.org", source="s"),
        ]
    )
    db.flush()
    db.add(DonorIdentity(donor_id=b.id, kind="email", value_norm="a@example.org", source="s"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_same_identity_value_may_exist_for_different_kinds(db: Session) -> None:
    a = donor(db)
    db.add_all(
        [
            DonorIdentity(donor_id=a.id, kind="phone", value_norm="+15205550100", source="s"),
            DonorIdentity(donor_id=a.id, kind="sheet_row", value_norm="+15205550100", source="s"),
        ]
    )
    db.flush()


def test_donor_email_is_case_insensitive(db: Session) -> None:
    donor(db, email="Ada@Example.org")
    found = db.execute(select(Donor).where(Donor.email == "ada@example.ORG")).scalar_one()
    assert found.display_name == "Ada Lovelace"


def test_trigram_search_finds_typos(db: Session) -> None:
    donor(db, "Katherine Johnson")
    hit = db.execute(
        select(func.count())
        .select_from(Donor)
        .where(Donor.display_name.op("%")("Katharine Jonson"))
    ).scalar_one()
    assert hit == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"gross_cents": 0, "net_cents": 0},  # must be positive
        {"gross_cents": -5, "net_cents": -5},
        {"fee_cents": 100, "net_cents": 5000},  # net must equal gross - fee
        {"fee_cents": 6000, "net_cents": -1000},  # fee cannot exceed gross
        {"currency": "EUR"},  # USD only (D-116)
        {"attribution": "zzz"},
        {"source": "paypal"},
    ],
)
def test_gift_checks(db: Session, overrides: dict) -> None:
    d = donor(db)
    with pytest.raises(IntegrityError):
        gift(db, d, **overrides)


def test_donor_present_exactly_when_linked(db: Session) -> None:
    d = donor(db)
    with pytest.raises(IntegrityError):
        gift(db, d, key="a", attribution="anonymous")  # donor set but not linked
    db.rollback()
    d = donor(db)
    with pytest.raises(IntegrityError):
        gift(db, None, key="b", attribution="linked")  # linked without donor
    db.rollback()
    gift(db, None, key="c", attribution="pending_review")  # pending has no donor yet


def test_row_key_is_unique_among_live_gifts_only(db: Session) -> None:
    d = donor(db)
    first = gift(db, d, key="same")
    with pytest.raises(IntegrityError):
        gift(db, d, key="same")
    db.rollback()
    d = donor(db)
    first = gift(db, d, key="same")
    first.deleted_at = func.now()  # soft delete frees the key (batch reverse, DED-2)
    db.flush()
    gift(db, d, key="same")


def test_committed_file_hash_is_unique_per_source(db: Session) -> None:
    u = User(email="u@example.org", display_name="U", password_hash="x")
    db.add(u)
    db.flush()

    def batch(source: str, status: str) -> None:
        db.add(
            ImportBatch(
                source=source, filename="f.csv", file_sha256="abc", uploaded_by=u.id, status=status
            )
        )
        db.flush()

    batch("zeffy", "committed")
    batch("zeffy", "previewed")  # previews may repeat
    batch("benevity", "committed")  # same hash, other source
    with pytest.raises(IntegrityError):
        batch("zeffy", "committed")


def test_source_program_map_unique_and_cascade_free(db: Session) -> None:
    p = program(db, "Summer Camp")
    db.add(SourceProgramMap(source="zeffy", source_value_norm="summer camp 2026", program_id=p.id))
    db.flush()
    db.add(SourceProgramMap(source="zeffy", source_value_norm="summer camp 2026", program_id=p.id))
    with pytest.raises(IntegrityError):
        db.flush()
