"""Field definitions, seeded built-ins and per-type value validation (CUS-1, CUS-3, D-141)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import FieldDefinition
from app.errors import Unprocessable
from app.services.fields import values
from tests import seed


def fd(key: str, type_: str, **kw) -> FieldDefinition:
    kw.setdefault("label", key.title())
    return FieldDefinition(
        entity="donor", key=key, type=type_, is_builtin=False, is_active=True, **kw
    )


def test_built_ins_are_seeded_for_donors_and_gifts(db: Session) -> None:
    rows = db.execute(select(FieldDefinition).order_by(FieldDefinition.position)).scalars().all()
    keys = {e: [r.key for r in rows if r.entity == e] for e in ("donor", "gift")}
    assert keys["donor"] == [
        "first_name", "last_name", "organization", "email", "phone", "notes", "kind",
    ]  # fmt: skip
    assert keys["gift"] == ["gift_date", "amount", "program", "campaign", "payer"]
    assert all(r.is_builtin and r.is_active for r in rows)
    assert {r.key for r in rows if r.is_contact} == {"email", "phone"}  # DON-3 applies


def test_custom_values_default_to_empty_and_keys_are_unique_per_entity(db: Session) -> None:
    donor = seed.add_donor(db, "Dee Donor")
    db.commit()
    assert (
        db.execute(text("SELECT custom FROM donors WHERE id = :i"), {"i": donor}).scalar_one() == {}
    )
    indexes = set(
        db.execute(
            text("SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_%_custom'")
        ).scalars()
    )
    assert indexes == {"ix_donors_custom", "ix_gifts_custom"}
    db.add(FieldDefinition(entity="gift", key="amount", label="Again", type="text"))
    with pytest.raises(IntegrityError):
        db.flush()  # the same key on the same entity is refused
    db.rollback()


GOOD = [
    (fd("t", "text"), "  hello ", "hello"),
    (fd("l", "long_text"), "a" * 600, "a" * 600),
    (fd("n", "number"), "1,250.5", 1250.5),
    (fd("n", "number"), 7, 7),
    (fd("m", "money"), "$25.50", 2550),
    (fd("m", "money"), 1000, 1000),
    (fd("d", "date"), "11/15/2026", "2026-11-15"),
    (fd("b", "bool"), "Yes", True),
    (fd("c", "choice", choices=["Gold", "Silver"]), "Gold", "Gold"),
    (fd("x", "multi_choice", choices=["A", "B"]), ["A", "B", "A"], ["A", "B"]),
    (fd("x", "multi_choice", choices=["A", "B"]), "A;B", ["A", "B"]),
]
BAD = [
    (fd("t", "text"), 5),
    (fd("t", "text"), "a" * 501),
    (fd("n", "number"), "lots"),
    (fd("n", "number"), True),
    (fd("m", "money"), 25.5),
    (fd("m", "money"), "-3"),
    (fd("d", "date"), "next week"),
    (fd("d", "date"), 46000),
    (fd("b", "bool"), "maybe"),
    (fd("c", "choice", choices=["Gold"]), "Bronze"),
    (fd("x", "multi_choice", choices=["A"]), ["A", "Z"]),
]


@pytest.mark.parametrize("defn,raw,stored", GOOD)
def test_good_values_are_stored_in_canonical_form(defn, raw, stored) -> None:
    assert values.validate([defn], {defn.key: raw}) == {defn.key: stored}


@pytest.mark.parametrize("defn,raw", BAD)
def test_bad_values_are_refused_with_the_field_label(defn, raw) -> None:
    with pytest.raises(Unprocessable) as err:
        values.validate([defn], {defn.key: raw})
    assert err.value.status == 422 and err.value.message.startswith(f"{defn.label}:")


def test_required_unknown_builtin_and_deactivated_fields() -> None:
    need, off = fd("need", "text", label="Tier", is_required=True), fd("off", "text", label="Old")
    off.is_active = False
    built = fd("email", "text", label="Email")
    built.is_builtin = True
    defs = [need, off, built]
    with pytest.raises(Unprocessable, match="Tier is required"):
        values.validate(defs, {}, creating=True)
    assert values.validate(defs, {}, {"need": "x"}) == {"need": "x"}  # edits need not resend it
    with pytest.raises(Unprocessable, match="Tier is required"):
        values.validate(defs, {"need": None}, {"need": "x"})
    for key, why in (("nope", "Unknown"), ("off", "deactivated"), ("email", "built-in")):
        with pytest.raises(Unprocessable, match=why):
            values.validate(defs, {key: "v"}, {"need": "x"})


def test_visible_hides_inactive_and_contact_values_from_those_without_access() -> None:
    plain, secret, off = (
        fd("plain", "text"),
        fd("secret", "text", is_contact=True),
        fd("off", "text"),
    )
    off.is_active = False
    stored = {"plain": "a", "secret": "b", "off": "c", "gone": "d"}
    defs = [plain, secret, off]
    assert values.visible(defs, stored, can_see_contact=False) == {"plain": "a"}
    assert values.visible(defs, stored, can_see_contact=True) == {"plain": "a", "secret": "b"}
