"""Import maps columns to custom fields and lists the rest as ignored (ING-14, CUS-4)."""

from sqlalchemy import select

from app.db.models import Donor, FieldDefinition, Gift
from tests.integration.test_import_commit import (  # noqa: F401
    commit,
    count,
    preview,
    world,
)

CSV = (
    b"Date,Amount,Platform,Donor name,Email,Transaction ID,"
    b"Giving Tier,check_number,Region,Pledged\n"
    b"2026-11-14,25,other,Ada Jones,ada@example.org,G1,Gold,1042,West,$1000\n"
    b"2026-11-13,30,other,Bo Lee,bo@example.org,G2,Bronze,7,East,\n"
)


def add_fields(db) -> None:
    db.add_all([
        FieldDefinition(entity="donor", key="giving_tier", label="Giving Tier", type="choice",
                        choices=["Gold", "Silver"]),
        FieldDefinition(entity="gift", key="check_number", label="Check number", type="number"),
        FieldDefinition(entity="donor", key="old", label="Region", type="text", is_active=False),
    ])  # fmt: skip
    db.commit()


def test_matching_columns_import_bad_values_invalidate_the_row_and_the_rest_are_ignored(
    db,
    world,  # noqa: F811
) -> None:
    add_fields(db)
    body = preview(world, CSV)
    assert [r["row_number"] for r in body["invalid_rows"]] == [2]
    assert body["invalid_rows"][0]["reason"].startswith("Giving Tier:")
    assert body["summary"]["reconciles"] and body["commit_allowed"]
    ignored = {c["header"]: c for c in body["ignored_columns"]}
    assert set(ignored) == {"Region", "Pledged"}  # a deactivated field's column is ignored too
    assert (
        ignored["Region"]["guessed_type"] == "text"
        and ignored["Region"]["suggested_entity"] == "gift"
    )

    commit(world, body)
    donor = db.scalar(select(Donor).where(Donor.display_name == "Ada Jones"))
    gift = db.scalar(select(Gift).where(Gift.donor_id == donor.id))
    assert donor.custom == {"giving_tier": "Gold"} and gift.custom == {"check_number": 1042}
    assert count(db, Donor, Donor.display_name == "Bo Lee") == 0  # the invalid row imported nothing


def test_custom_columns_do_not_change_row_keys_so_a_reimport_is_still_recognised(
    db,
    world,  # noqa: F811
) -> None:
    add_fields(db)
    plain = (
        b"Date,Amount,Platform,Donor name,Email,Transaction ID\n"
        b"2026-11-14,25,other,Ada Jones,ada@example.org,G1\n"
    )
    commit(world, preview(world, plain))
    again = preview(world, CSV)
    assert again["summary"]["already_imported"]["count"] == 1
