"""DED-3 precedence, explicit decision memory, and the independent fixture oracle."""

import json
from pathlib import Path

from app.services.dedupe.resolver import IdentityIndex, fingerprint
from app.services.ingest.adapters import IncomingDonor, parse_upload


def donor(**changes):
    return IncomingDonor(
        display_name="Ada Jones",
        first_name="Ada",
        last_name="Jones",
        email="ada@example.org",
        phone="+16025550100",
        **changes,
    )


def test_platform_id_precedes_conflicting_email_and_names():
    original = donor()
    index = IdentityIndex({1: original}, [(1, "zeffy_contact", "C1")])
    incoming = original.model_copy(
        update={"first_name": "Bea", "last_name": "Smith", "zeffy_contact": "C1"}
    )
    assert index.resolve(incoming).donor_id == 1
    assert index.resolve(incoming).verdict == "link"


def test_email_links_but_conflicting_names_and_phone_only_require_review():
    original = donor()
    index = IdentityIndex({1: original})
    assert (
        index.resolve(original.model_copy(update={"email": " ADA@EXAMPLE.ORG "})).verdict == "link"
    )
    conflict = original.model_copy(update={"first_name": "Bea"})
    result = index.resolve(conflict)
    assert result.verdict == "review" and result.reason == "name_conflict"
    phone = original.model_copy(update={"email": "work@example.org"})
    assert index.resolve(phone).reason == "phone"


def test_employer_match_reviews_all_candidates_but_name_alone_never_links():
    first = donor(organization="Example Inc")
    second = first.model_copy(update={"email": "other@example.org", "phone": ""})
    index = IdentityIndex({1: first, 2: second})
    incoming = first.model_copy(update={"email": "", "phone": ""})
    assert index.resolve(incoming).candidates == [1, 2]
    assert index.resolve(incoming).reason == "name_employer"
    assert index.resolve(incoming.model_copy(update={"organization": ""})).verdict == "new"


def test_explicit_household_decision_is_remembered_without_linking_on_name_alone():
    first = donor()
    incoming = first.model_copy(update={"display_name": "Bea Jones", "first_name": "Bea"})
    index = IdentityIndex({1: first, 2: incoming}, remembered={fingerprint(incoming): 2})
    assert index.resolve(incoming).donor_id == 2
    anonymous = IdentityIndex({1: first}, remembered={fingerprint(incoming): None})
    assert anonymous.resolve(incoming).verdict == "anonymous"
    no_identity = incoming.model_copy(update={"email": "", "phone": ""})
    assert fingerprint(no_identity) == ""


def test_phone_review_decision_survives_a_later_email_being_added():
    incoming = donor().model_copy(update={"email": ""})
    index = IdentityIndex({1: donor(), 2: incoming}, remembered={fingerprint(incoming): 2})
    later = incoming.model_copy(update={"email": "work@example.org"})
    assert index.resolve(later).verdict == "link"
    assert index.resolve(later).donor_id == 2


def test_known_email_precedes_a_weaker_phone_decision_for_a_namesake():
    first = donor()
    incoming = first.model_copy(update={"email": ""})
    index = IdentityIndex({1: first, 2: incoming}, remembered={fingerprint(incoming): 2})
    assert index.resolve(first).donor_id == 1


def test_production_resolver_matches_all_fixture_donors_and_review_reasons():
    fixture = Path(__file__).resolve().parents[3] / "fixtures"
    manifest = json.loads((fixture / "manifest.json").read_text())
    index, reviews = IdentityIndex(), []
    for source, filename in zip(
        ["spreadsheet", "zeffy", "benevity", "generic"], manifest["import_order"], strict=True
    ):
        for row in parse_upload(source, filename, (fixture / filename).read_bytes()):
            if row.reason or row.donor.anonymous:
                continue
            result = index.resolve(row.donor)
            if result.verdict == "new":
                index.create(row.donor)
            elif result.verdict == "link":
                index.learn(result.donor_id, row.donor)
            elif result.verdict == "review":
                reason = "household" if source == "spreadsheet" else result.reason
                reviews.append({"file": filename, "row": row.row_number, "reason": reason})
    assert len(index.donors) == manifest["donors_created_after_all_imports"] == 225
    assert reviews == manifest["review_items"]
