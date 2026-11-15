"""Attach anonymous revenue to a donor without changing ownership or logging contact."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.repos import dedupe, ownership
from app.schemas.donors import GiftOut


def attribute(db: Session, actor: Actor, clock: Clock, gift_id: int, donor_id: int) -> GiftOut:
    dedupe.require(actor)
    ownership.lock(db, actor, action="review.decide")
    gift = dedupe.anonymous_gift(db, actor, gift_id)
    donor = dedupe.active_donor(db, actor, donor_id)
    cutoff = today(clock) - timedelta(days=dedupe.cutoff_days(db, actor))
    dedupe.attribute_gift(db, actor, gift, donor, at=clock.now(), cutoff=cutoff)
    # The linked gift appears in the existing donor timeline. Data attribution
    # does not count as donor contact or clear a quarterly-touch reminder.
    return GiftOut(**dedupe.gift_output(db, actor, gift, donor))
