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
from app.services.donors import service as donor_service
from app.services.fields import service as fields
from app.services.fields import values
from app.services.fields.view import FieldView

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
    custom = values.validate(fields.definitions(db, "gift"), body.custom or {}, creating=True)
    # An old check typed in today is history, not a thank-you owed (same rule as ING-11).
    assumed = body.gift_date < day - timedelta(days=dedupe.cutoff_days(db, actor))
    gift = writes.add_manual_gift(
        db, actor, donor_id, gift_date=body.gift_date, gross_cents=body.gross_cents,
        program_id=body.program_id, assumed_thanked=assumed, at=clock.now(), custom=custom,
    )  # fmt: skip
    return donor_service.gift_out(reads.gift_row(db, actor, gift.id), FieldView(db, actor))
