"""Gift identity survives reordering and overlapping files (DATA_MODEL 3.1)."""

from collections import Counter
from datetime import date
from hashlib import sha256

from app.services.ingest.adapters import IncomingDonor, IncomingGift
from app.services.ingest.row_keys import row_key


def gift(**changes):
    return IncomingGift(gift_date=date(2026, 11, 14), gross_cents=5000, net_cents=5000, **changes)


def test_transaction_id_uses_version_and_source():
    g = gift(source_txn_id="T1")
    key = row_key("zeffy", IncomingDonor(), g, Counter())
    assert key == sha256(b"v1|zeffy|T1").hexdigest()
    assert key != row_key("benevity", IncomingDonor(), g, Counter())
    assert key != row_key("zeffy", IncomingDonor(), gift(source_txn_id="T1:match"), Counter())


def test_occurrences_preserve_identical_gifts_and_survive_shuffle():
    donor = IncomingDonor(email="ada@example.org", display_name="Ada Jones")
    a, b = gift(source_platform="azgives"), gift(source_platform="united_way")

    def keys(gifts):
        occurrences = Counter()
        return sorted(row_key("generic", donor, g, occurrences) for g in gifts)

    assert len(set(keys([a, a]))) == 2
    assert keys([a, b, a]) == keys([b, a, a])
    assert keys([a])[0] in keys([a, b])


def test_donor_key_uses_email_then_platform_id_then_name_then_anon():
    g = gift(source_platform="other")
    for donor, identity in [
        (IncomingDonor(email=" ADA@example.org ", zeffy_contact="C1"), "ada@example.org"),
        (IncomingDonor(zeffy_contact="C1", display_name="Ada"), "C1"),
        (IncomingDonor(display_name="Dr. Ada Jones"), "ada jones"),
        (IncomingDonor(), "anon"),
    ]:
        expected = f"v1|generic|other|{identity}|2026-11-14|5000|1"
        assert row_key("generic", donor, g, Counter()) == sha256(expected.encode()).hexdigest()
