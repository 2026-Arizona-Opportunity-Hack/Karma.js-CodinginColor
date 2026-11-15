"""The import contract separates physical rows, gifts and employer-match revenue."""

import pytest
from pydantic import ValidationError

from app.schemas.imports import ImportClassSummary, ImportSummary


def summary(**changes):
    empty = ImportClassSummary(count=0, cents=0, gift_count=0, donation_cents=0, match_cents=0)
    values = dict(
        rows_read=1,
        gift_count=2,
        donation_cents=10000,
        match_cents=5000,
        total_cents=15000,
        new_gifts=ImportClassSummary(
            count=1, cents=15000, gift_count=2, donation_cents=10000, match_cents=5000
        ),
        already_imported=empty,
        needs_review=empty,
        invalid=empty,
        anonymous=empty,
        new_donors=1,
        donors_matched=0,
        unmapped_campaigns=[],
    )
    return ImportSummary(**(values | changes))


def test_one_source_row_can_produce_two_gifts_and_both_kinds_of_cents():
    value = summary()
    assert value.rows_read == 1 and value.gift_count == 2
    assert value.new_gifts.donation_cents == 10000
    assert value.new_gifts.match_cents == 5000
    assert value.rows_reconcile and value.cents_reconcile and value.reconciles


@pytest.mark.parametrize(
    "changes,rows,cents",
    [
        ({"rows_read": 2}, False, True),
        ({"total_cents": 15001}, True, False),
        ({"donation_cents": 15000, "match_cents": 0}, True, False),
    ],
)
def test_reconciliation_is_computed_not_trusted(changes, rows, cents):
    value = summary(**(changes | {"reconciles": True}))
    assert value.rows_reconcile is rows and value.cents_reconcile is cents
    assert not value.reconciles


def test_gift_count_is_reconciled_separately_from_source_rows():
    assert not summary(gift_count=1).reconciles


def test_class_cents_must_equal_donations_plus_matches():
    with pytest.raises(ValidationError, match="donation"):
        ImportClassSummary(
            count=1, cents=15001, gift_count=2, donation_cents=10000, match_cents=5000
        )
