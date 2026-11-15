"""Proposal-only contacts must not affect subsequent spreadsheet matching."""

import pytest

from app.errors import Invalid
from app.services.dedupe.resolver import fingerprint
from app.services.ingest.adapters import IncomingDonor
from tests.unit.test_import_preview import preview, snapshot


def profile(**fields):
    return IncomingDonor(
        display_name="Ada Jones", first_name="Ada", last_name="Jones", **fields
    )


def test_proposed_contact_is_not_matching_evidence_for_later_rows():
    state = preview(
        b"Name,Contact ID,Email\nAda Jones,C1,new@example.org\n"
        b"Ada Jones,,new@example.org\n",
        source="spreadsheet",
        snap=snapshot(
            donors={7: profile(email="old@example.org")},
            identities=[(7, "zeffy_contact", "C1")],
        ),
    )
    assert state.rows[0].donor_token == 7
    assert state.rows[1].donor_token < 0
    assert state.output.summary.new_donors == state.output.summary.updated_count == 1
    assert state.output.summary.reconciles


@pytest.mark.parametrize("remembered", [False, True])
def test_email_or_remembered_match_proposes_updates(remembered):
    incoming = profile(email="known@example.org", notes="New note")
    state = preview(
        b"Name,Email,Notes\nAda Jones,known@example.org,New note\n",
        source="spreadsheet",
        snap=snapshot(
            donors={7: profile(email="old@example.org" if remembered else incoming.email)},
            remembered={fingerprint(incoming): 7} if remembered else {},
        ),
    )
    assert state.output.updates[0].donor_id == 7
    assert state.output.updates[0].changes["notes"].new_value == "New note"
    assert state.output.summary.reconciles


def test_conflicting_repeated_donor_values_reject_preview():
    with pytest.raises(Invalid, match="Conflicting spreadsheet updates"):
        preview(
            b"Name,Contact ID,Notes\nAda Jones,C1,New note\nAda Jones,C1,Old note\n",
            source="spreadsheet",
            snap=snapshot(
                donors={7: profile(notes="Old note")},
                identities=[(7, "zeffy_contact", "C1")],
            ),
        )
