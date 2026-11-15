"""Add a gift by hand (DON-8)."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.errors import Invalid
from app.repos import dedupe
from app.repos import donor_writes as writes
from app.repos import donors as reads
from app.schemas.donors import GiftCreate, GiftOut

NOTE_UNSUPPORTED = (
    "Gift notes are not stored yet. Put the note on the donor, or log it as a contact."
)


def add_gift(db: Session, clock: Clock, actor: Actor, donor_id: int, body: GiftCreate) -> GiftOut:
    day = today(clock)
    if body.gift_date > day:
        raise Invalid("A gift cannot be dated in the future.")
    if body.note:
        # The gifts table has no note column, gift history is visible to every member (D-104)
        # and a note may hold personal details, so refuse rather than drop or expose it.
        raise Invalid(NOTE_UNSUPPORTED)
    # An old check typed in today is history, not a thank-you owed (same rule as ING-11).
    assumed = body.gift_date < day - timedelta(days=dedupe.cutoff_days(db, actor))
    gift = writes.add_manual_gift(
        db, actor, donor_id, gift_date=body.gift_date, gross_cents=body.gross_cents,
        program_id=body.program_id, assumed_thanked=assumed, at=clock.now(),
    )  # fmt: skip
    return GiftOut(**reads.gift_row(db, actor, gift.id))
