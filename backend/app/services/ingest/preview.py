"""Read-only preview planning. Summary class counts are physical file rows.

One Benevity row may carry multiple gifts; its cents include all gifts. `anonymous`
is a subset of new rows, not another term in the conservation equation. Spreadsheet
donor-only rows occupy new/already-imported/review classes with zero gift cents.
"""

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from secrets import randbits
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field

from app.clock import Clock, today
from app.errors import NotFound
from app.schemas.common import ImportSource, MemberRef
from app.schemas.imports import (
    ImportBatchOut,
    ImportClassSummary,
    ImportPreviewOut,
    ImportSummary,
    InvalidRow,
)
from app.services.dedupe.resolver import IdentityIndex
from app.services.ingest.adapters import IncomingDonor, IncomingGift, IncomingRow
from app.services.ingest.row_keys import row_key
from app.services.ingest.uploads import UploadTooLarge


@dataclass
class Snapshot:
    member: MemberRef
    general_program: int
    cutoff_days: int = 60
    row_keys: set[str] = field(default_factory=set)
    programs: dict[str, int] = field(default_factory=dict)
    donors: dict[int, IncomingDonor] = field(default_factory=dict)
    identities: list[tuple[int, str, str]] = field(default_factory=list)
    remembered: dict[str, int | None] = field(default_factory=dict)


class PlannedGift(BaseModel):
    gift: IncomingGift
    row_key: str
    program_id: int
    assumed_thanked: bool
    already_imported: bool


class PlannedRow(BaseModel):
    incoming: IncomingRow
    status: Literal["new", "already_imported", "needs_review", "invalid"]
    donor_token: int | None = None
    candidates: list[int] = Field(default_factory=list)
    reason: str | None = None
    gifts: list[PlannedGift] = Field(default_factory=list)


class PreviewState(BaseModel):
    output: ImportPreviewOut
    file_sha256: str
    rows: list[PlannedRow]
    expires_at: datetime


def build_preview(
    source: ImportSource,
    filename: str,
    data: bytes,
    incoming: list[IncomingRow],
    snapshot: Snapshot,
    clock: Clock,
) -> PreviewState:
    cutoff = today(clock) - timedelta(days=snapshot.cutoff_days)
    resolver = IdentityIndex(snapshot.donors, snapshot.identities, snapshot.remembered)
    occurrences: Counter[str] = Counter()
    seen = snapshot.row_keys.copy()
    counts: Counter[str] = Counter()
    gift_counts: Counter[str] = Counter()
    donations: Counter[str] = Counter()
    matches: Counter[str] = Counter()
    rows: list[PlannedRow] = []
    unmapped: set[str] = set()
    created: set[int] = set()
    matched: set[int] = set()
    for incoming_row in incoming:
        row = PlannedRow(incoming=incoming_row, status="new", reason=incoming_row.reason)
        rows.append(row)
        for gift in incoming_row.gifts:
            key = row_key(source, incoming_row.donor, gift, occurrences)
            campaign = gift.campaign_name.strip().lower()
            program = snapshot.programs.get(campaign, snapshot.general_program)
            if campaign and campaign not in snapshot.programs:
                unmapped.add(gift.campaign_name)
            row.gifts.append(
                PlannedGift(
                    gift=gift,
                    row_key=key,
                    program_id=program,
                    assumed_thanked=gift.gift_date < cutoff,
                    already_imported=key in seen,
                )
            )
            seen.add(key)
        if row.reason:
            row.status = "invalid"
        elif row.gifts and all(g.already_imported for g in row.gifts):
            row.status = "already_imported"
        elif not incoming_row.donor.anonymous:
            result = resolver.resolve(incoming_row.donor)
            did, row.candidates, row.reason = result.donor_id, result.candidates, result.reason
            if result.verdict == "anonymous":
                row.incoming = incoming_row.model_copy(
                    update={"donor": incoming_row.donor.model_copy(update={"anonymous": True})}
                )
            elif row.candidates:
                row.status = "needs_review"
                if source == "spreadsheet" and row.reason == "name_conflict":
                    row.reason = "household"
            else:
                if did is None:
                    did = resolver.create(incoming_row.donor)
                    created.add(did)
                else:
                    resolver.learn(did, incoming_row.donor)
                    if did > 0:
                        matched.add(did)
                    if source == "spreadsheet":
                        row.status = "already_imported"
                row.donor_token = did
        donation = sum(g.gift.gross_cents for g in row.gifts if not g.gift.is_matching_gift)
        match = sum(g.gift.gross_cents for g in row.gifts if g.gift.is_matching_gift)
        counts[row.status] += 1
        gift_counts[row.status] += len(row.gifts)
        donations[row.status] += donation
        matches[row.status] += match
        if row.status == "new" and row.incoming.donor.anonymous:
            counts["anonymous"] += 1
            gift_counts["anonymous"] += len(row.gifts)
            donations["anonymous"] += donation
            matches["anonymous"] += match

    def bucket(status: str) -> ImportClassSummary:
        return ImportClassSummary(
            count=counts[status],
            gift_count=gift_counts[status],
            cents=donations[status] + matches[status],
            donation_cents=donations[status],
            match_cents=matches[status],
        )

    # Independent source totals make a missing or corrupted planned gift fail
    # reconciliation even if the physical-row counts still add up.
    source_gifts = [gift for row in incoming for gift in row.gifts]
    donation_total = sum(g.gross_cents for g in source_gifts if not g.is_matching_gift)
    match_total = sum(g.gross_cents for g in source_gifts if g.is_matching_gift)
    summary = ImportSummary(
        rows_read=len(incoming),
        gift_count=len(source_gifts),
        donation_cents=donation_total,
        match_cents=match_total,
        total_cents=donation_total + match_total,
        new_gifts=bucket("new"),
        already_imported=bucket("already_imported"),
        needs_review=bucket("needs_review"),
        invalid=bucket("invalid"),
        anonymous=bucket("anonymous"),
        new_donors=len(created),
        donors_matched=len(matched),
        unmapped_campaigns=sorted(unmapped),
    )
    batch = ImportBatchOut(
        id=randbits(52) or 1,
        source=source,
        filename=filename,
        status="previewed",
        uploaded_by=snapshot.member,
        created_at=clock.now(),
        cutoff_date=cutoff,
        summary=summary,
    )
    return PreviewState(
        output=ImportPreviewOut(
            batch=batch,
            summary=summary,
            commit_allowed=summary.reconciles,
            invalid_rows=[
                InvalidRow(row_number=r.incoming.row_number, reason=r.reason or "invalid")
                for r in rows
                if r.status == "invalid"
            ],
        ),
        file_sha256=sha256(data).hexdigest(),
        rows=rows,
        expires_at=clock.now() + timedelta(minutes=20),
    )


class PreviewStore:
    """Single-worker previews: 20 minute TTL, bounded entries and serialized bytes.

    A restart or eviction safely requires re-upload. Commit must revalidate against
    current database state; a cached preview is never authoritative for writes.
    """

    def __init__(self, *, max_entries: int = 16, max_bytes: int = 32 * 1024 * 1024) -> None:
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._entries: OrderedDict[int, tuple[PreviewState, int]] = OrderedDict()
        self._lock = RLock()

    def put(self, state: PreviewState, clock: Clock) -> None:
        size = len(state.model_dump_json().encode())
        if size > self.max_bytes:
            raise UploadTooLarge("Normalized preview is too large. Split the file.")
        with self._lock:
            self._expire(clock)
            self._entries[state.output.batch.id] = (state.model_copy(deep=True), size)
            while (
                len(self._entries) > self.max_entries
                or sum(size for _, size in self._entries.values()) > self.max_bytes
            ):
                self._entries.popitem(last=False)

    def _expire(self, clock: Clock) -> None:
        for key, (state, _) in list(self._entries.items()):
            if state.expires_at <= clock.now():
                del self._entries[key]

    def get(self, batch_id: int, clock: Clock) -> PreviewState:
        with self._lock:
            self._expire(clock)
            entry = self._entries.get(batch_id)
            if entry is None:
                raise NotFound("Preview expired or unavailable. Upload the file again.")
            return entry[0].model_copy(deep=True)


previews = PreviewStore()
