"""Preview row accounting and bounded, expiring state without database writes."""

from datetime import UTC, datetime, timedelta

import pytest

from app.clock import FixedClock
from app.errors import NotFound
from app.schemas.common import MemberRef
from app.services.ingest.adapters import parse_upload
from app.services.ingest.preview import PreviewStore, Snapshot, build_preview

CLOCK = FixedClock(datetime(2026, 11, 15, 2, tzinfo=UTC))


def snapshot(**kw):
    return Snapshot(member=MemberRef(id=1, display_name="Ada"), general_program=5, **kw)


def preview(data, source="generic", snap=None):
    rows = parse_upload(source, "a.csv", data)
    return build_preview(source, "a.csv", data, rows, snap or snapshot(), CLOCK)


def test_summary_includes_invalid_anonymous_program_fallback_and_cutoff():
    state = preview(
        b"Date,Amount,Platform,Campaign\n2026-09-14,10,other,Unknown\n"
        b"2026-09-15,20,other,Camp\ninvalid,30,other,Camp\n",
        snap=snapshot(programs={"camp": 2}),
    )
    summary = state.output.summary
    assert summary.rows_read == 3
    assert summary.new_gifts.count == 2 and summary.new_gifts.cents == 3000
    assert summary.anonymous.count == 2 and summary.invalid.count == 1
    assert summary.unmapped_campaigns == ["Unknown"]
    assert summary.reconciles
    assert state.output.batch.cutoff_date.isoformat() == "2026-09-15"
    first, second = state.rows[:2]
    assert first.gifts[0].assumed_thanked
    assert not second.gifts[0].assumed_thanked
    assert second.gifts[0].program_id == 2
    assert state.output.invalid_rows[0].reason == "bad_date"


def test_existing_and_duplicate_within_file_keys_are_already_imported():
    data = b"Date,Amount,Payment ID\n2026-11-14,10,T1\n2026-11-14,10,T1\n"
    first = preview(data, source="zeffy")
    assert first.output.summary.new_gifts.count == 1
    assert first.output.summary.already_imported.count == 1
    key = first.rows[0].gifts[0].row_key
    repeated = preview(data, source="zeffy", snap=snapshot(row_keys={key}))
    assert repeated.output.summary.new_gifts.count == 0
    assert repeated.output.summary.already_imported.count == 2


def test_benevity_summary_counts_source_rows_and_includes_match_cents():
    state = preview(
        b"Transaction ID,Donation Date,Donation Amount,Match Amount,Donation Currency\n"
        b"T1,2026-11-14,100,50,USD\n",
        source="benevity",
    )
    summary = state.output.summary
    assert summary.rows_read == summary.new_gifts.count == 1
    assert summary.new_gifts.cents == 15000
    assert summary.gift_count == summary.new_gifts.gift_count == 2
    assert summary.new_gifts.donation_cents == summary.donation_cents == 10000
    assert summary.new_gifts.match_cents == summary.match_cents == 5000
    assert summary.total_cents == 15000
    assert summary.rows_reconcile and summary.cents_reconcile
    assert len(state.rows[0].gifts) == 2


def test_benevity_fixture_summary_has_80_rows_and_91_gifts():
    from pathlib import Path

    data = (
        Path(__file__).resolve().parents[3] / "fixtures" / "synthetic_benevity_like.csv"
    ).read_bytes()
    summary = preview(data, source="benevity").output.summary
    assert summary.rows_read == 80 and summary.gift_count == 91
    assert summary.donation_cents == 597500 and summary.match_cents == 101250
    assert summary.total_cents == 698750
    assert summary.anonymous.count == 10 and summary.anonymous.gift_count == 13
    assert summary.invalid.count == 4 and summary.invalid.gift_count == 0
    assert summary.reconciles and summary.rows_reconcile and summary.cents_reconcile


def test_bad_planned_cents_disable_commit_even_when_rows_reconcile(monkeypatch):
    import app.services.ingest.preview as module

    constructor = module.PlannedGift

    def corrupt(**kwargs):
        gift = kwargs["gift"]
        kwargs["gift"] = gift.model_copy(update={"gross_cents": gift.gross_cents + 1})
        return constructor(**kwargs)

    monkeypatch.setattr(module, "PlannedGift", corrupt)
    result = preview(b"Date,Amount,Platform\n2026-11-14,10,other\n").output
    assert result.summary.rows_reconcile
    assert not result.summary.cents_reconcile
    assert not result.commit_allowed


def test_spreadsheet_counts_donor_rows_without_creating_gifts():
    state = preview(
        b"Name,Email\nAda Jones,ada@example.org\nAda Jones,ada@example.org\n", source="spreadsheet"
    )
    summary = state.output.summary
    assert summary.rows_read == 2 and summary.new_donors == 1
    assert summary.new_gifts.count == summary.already_imported.count == 1
    assert summary.new_gifts.cents == 0
    assert summary.gift_count == 0 and summary.total_cents == 0
    assert all(not row.gifts for row in state.rows)


def test_preview_store_expires_evicts_and_returns_isolated_copies():
    state = preview(b"Date,Amount,Platform\n2026-11-14,10,other\n")
    store = PreviewStore(max_entries=1)
    store.put(state, CLOCK)
    copy = store.get(state.output.batch.id, CLOCK)
    copy.rows.clear()
    assert store.get(state.output.batch.id, CLOCK).rows
    next_state = preview(b"Date,Amount,Platform\n2026-11-14,20,other\n")
    store.put(next_state, CLOCK)
    with pytest.raises(NotFound):
        store.get(state.output.batch.id, CLOCK)
    later = FixedClock(CLOCK.now() + timedelta(minutes=21))
    with pytest.raises(NotFound, match="expired"):
        store.get(next_state.output.batch.id, later)


def test_preview_2000_rows_within_ten_seconds():
    from time import perf_counter

    data = b"Date,Amount,Platform,Donor name,Email\n" + (
        b"2026-11-14,10,other,Ada Jones,ada@example.org\n" * 2000
    )
    started = perf_counter()
    state = preview(data)
    assert perf_counter() - started < 10
    assert state.output.summary.new_donors == 1
    assert state.output.summary.new_gifts.count == 2000
    assert len({row.gifts[0].row_key for row in state.rows}) == 2000
