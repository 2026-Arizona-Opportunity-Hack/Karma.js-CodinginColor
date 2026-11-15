"""Versioned gift keys (DATA_MODEL 3.1). Counters are scoped to one complete file."""

from collections import Counter
from hashlib import sha256

from app.schemas.common import ImportSource
from app.services.ingest.adapters import IncomingDonor, IncomingGift
from app.services.ingest.normalizers import email, name


def row_key(
    source: ImportSource, donor: IncomingDonor, gift: IncomingGift, occurrences: Counter[str]
) -> str:
    if gift.source_txn_id:
        value = f"v1|{source}|{gift.source_txn_id}"
    else:
        identity = email(donor.email) or donor.zeffy_contact or name(donor.display_name) or "anon"
        base = (
            f"v1|{source}|{gift.source_platform}|{identity}|"
            f"{gift.gift_date.isoformat()}|{gift.gross_cents}"
        )
        occurrences[base] += 1
        value = f"{base}|{occurrences[base]}"
    return sha256(value.encode("utf-8")).hexdigest()
