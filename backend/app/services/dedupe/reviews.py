"""Human review decisions. The request owns one transaction for every change."""

from datetime import timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.errors import Conflict
from app.repos import dedupe as repo
from app.repos import imports, ownership
from app.schemas.imports import ReviewDecisionIn, ReviewListOut, ReviewOut
from app.services.dedupe.resolver import IdentityIndex, Resolution
from app.services.ingest.adapters import IncomingDonor
from app.services.ownership.assignment import assign_new


def candidates(db: Session, actor: Actor, incoming: IncomingDonor) -> Resolution:
    """Reusable DED-6 candidate matching for lane C's manual donor creation."""
    snapshot = imports.snapshot(db, actor, "spreadsheet", b"")
    return IdentityIndex(snapshot.donors, snapshot.identities, snapshot.remembered).resolve(
        incoming
    )


def list_reviews(db: Session, actor: Actor, status: Literal["open", "decided"]) -> ReviewListOut:
    return ReviewListOut(
        items=[
            ReviewOut(**repo.details(db, actor, review))
            for review in repo.list_reviews(db, actor, status)
        ]
    )


def decide(
    db: Session,
    actor: Actor,
    clock: Clock,
    review_id: int,
    body: ReviewDecisionIn,
) -> ReviewOut:
    repo.require(actor)
    ownership.lock(db, actor, action="review.decide")  # same lock order as import commit
    review = repo.get_review(db, actor, review_id)
    if review.status != "open":
        raise Conflict("This review was already decided.")
    incoming = IncomingDonor.model_validate(review.incoming)
    donor = None
    if body.decision == "link":
        assert body.donor_id is not None  # enforced by frozen request schema
        donor = repo.active_donor(db, actor, body.donor_id)
    elif body.decision == "create_new":
        donor = repo.create_donor(db, actor, incoming, clock.now())
        assign_new(db, actor, donor, clock, action="review.decide")
    cutoff = today(clock) - timedelta(days=repo.cutoff_days(db, actor))
    repo.apply_decision(db, actor, review, body.decision, donor, incoming, clock.now(), cutoff)
    return ReviewOut(**repo.details(db, actor, review))
