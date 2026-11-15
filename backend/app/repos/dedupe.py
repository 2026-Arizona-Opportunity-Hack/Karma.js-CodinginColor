"""Review storage and identity learning. Every entry point takes Actor and checks policy."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.authz import policy
from app.authz.actor import Actor
from app.db.models import (
    AppSetting,
    Donor,
    DonorIdentity,
    Gift,
    ImportBatch,
    ImportRow,
    MatchReview,
    Program,
    User,
)
from app.errors import Conflict, Forbidden, Invalid, NotFound
from app.repos import audit
from app.repos.ownership import AssignmentAction
from app.services.dedupe.resolver import fingerprint, fingerprints, identity_keys
from app.services.ingest.adapters import IncomingDonor


def require(actor: Actor, action: AssignmentAction = "review.decide") -> None:
    if not policy.can(actor, action):
        raise Forbidden("You cannot decide donor identity reviews.")


def list_reviews(db: Session, actor: Actor, status: str) -> list[MatchReview]:
    require(actor)
    condition = MatchReview.status == "open" if status == "open" else MatchReview.status != "open"
    return list(db.scalars(select(MatchReview).where(condition).order_by(MatchReview.id)))


def get_review(db: Session, actor: Actor, review_id: int) -> MatchReview:
    require(actor)
    review = db.scalar(select(MatchReview).where(MatchReview.id == review_id).with_for_update())
    if review is None:
        raise NotFound("Review not found.")
    return review


def active_donor(
    db: Session, actor: Actor, donor_id: int, *, action: AssignmentAction = "review.decide"
) -> Donor:
    require(actor, action)
    donor = db.scalar(
        select(Donor)
        .where(Donor.id == donor_id, Donor.deleted_at.is_(None), Donor.merged_into_id.is_(None))
        .with_for_update()
    )
    if donor is None:
        raise NotFound("Donor not found.")
    return donor


def create_donor(
    db: Session,
    actor: Actor,
    incoming: IncomingDonor,
    at: datetime,
    *,
    action: AssignmentAction = "review.decide",
) -> Donor:
    require(actor, action)
    if not (incoming.display_name or incoming.email):
        raise Invalid("A donor name or email is required to create a donor.")
    donor = Donor(
        kind=incoming.kind,
        display_name=incoming.display_name or incoming.email,
        first_name=incoming.first_name or None,
        last_name=incoming.last_name or None,
        organization=incoming.organization or None,
        email=incoming.email or None,
        phone=incoming.phone or None,
        notes=incoming.notes or None,
        created_via="import",
        created_at=at,
        updated_at=at,
    )
    db.add(donor)
    db.flush()
    return donor


def anonymous_gift(db: Session, actor: Actor, gift_id: int) -> Gift:
    require(actor)
    gift = db.scalar(
        select(Gift).where(Gift.id == gift_id, Gift.deleted_at.is_(None)).with_for_update()
    )
    if gift is None:
        raise NotFound("Gift not found.")
    if gift.attribution != "anonymous":
        raise Conflict("Only anonymous gifts can be attributed. Use review for pending gifts.")
    return gift


def attribute_gift(
    db: Session, actor: Actor, gift: Gift, donor: Donor, *, at: datetime, cutoff: date
) -> None:
    require(actor)
    gift.donor_id, gift.attribution = donor.id, "linked"
    gift.assumed_thanked = gift.assumed_thanked or gift.gift_date < cutoff
    audit.write(
        db,
        actor,
        "gift.attribute",
        entity="gift",
        entity_id=gift.id,
        data={"donor_id": donor.id},
        at=at,
    )
    db.flush()


def gift_output(db: Session, actor: Actor, gift: Gift, donor: Donor) -> dict[str, Any]:
    require(actor)
    program = db.get(Program, gift.program_id)
    if program is None:
        raise NotFound("Gift program not found.")
    return {
        "id": gift.id,
        "donor_id": gift.donor_id,
        "donor_name": donor.display_name,
        "attribution": gift.attribution,
        "source": gift.source,
        "gift_date": gift.gift_date,
        "gross_cents": gift.gross_cents,
        "fee_cents": gift.fee_cents,
        "net_cents": gift.net_cents,
        "program": program.name,
        "campaign_name": gift.campaign_name,
        "is_matching_gift": gift.is_matching_gift,
        "payer_name": gift.payer_name,
        "assumed_thanked": gift.assumed_thanked,
    }


def learn(
    db: Session,
    actor: Actor,
    donor: Donor,
    incoming: IncomingDonor,
    source: str,
    *,
    at: datetime,
    action: AssignmentAction = "review.decide",
) -> None:
    require(actor, action)
    for kind, value in identity_keys(incoming):
        target = donor.id
        if kind in ("email", "phone"):
            column = Donor.email if kind == "email" else Donor.phone
            # Manual donors can predate identity rows. Reserve their original
            # primary contact before learning a conflicting incoming record.
            canonical = db.scalar(
                select(Donor.id)
                .where(
                    column == value,
                    Donor.deleted_at.is_(None),
                )
                .order_by(Donor.id)
                .limit(1)
            )
            if canonical is not None:
                target = canonical
        exists = db.scalar(
            select(DonorIdentity.id).where(
                DonorIdentity.donor_id == target,
                DonorIdentity.kind == kind,
                DonorIdentity.value_norm == value,
            )
        )
        if exists is None:
            if kind != "name_org":
                old = db.scalar(
                    select(DonorIdentity)
                    .where(
                        DonorIdentity.kind == kind,
                        DonorIdentity.value_norm == value,
                    )
                    .with_for_update()
                )
                previous = db.get(Donor, old.donor_id) if old else None
                if old and previous and previous.deleted_at is not None:
                    old.donor_id = target
                    continue
            # Conflicting household emails/phones remain with their existing donor.
            # The reviewed incoming fingerprint records the explicit exception.
            db.execute(
                insert(DonorIdentity)
                .values(
                    donor_id=target,
                    kind=kind,
                    value_norm=value,
                    source=source,
                    created_at=at,
                )
                .on_conflict_do_nothing()
            )


def cutoff_days(db: Session, actor: Actor) -> int:
    require(actor)
    setting = db.get(AppSetting, "import_cutoff_days")
    return int(setting.value) if setting else 60


def details(db: Session, actor: Actor, review: MatchReview) -> dict[str, Any]:
    require(actor)
    row = db.get(ImportRow, review.import_row_id) if review.import_row_id else None
    batch = db.get(ImportBatch, row.batch_id) if row else None
    reason = row.reason if row else review.incoming.get("_reason")
    match_reason = {"phone": "phone", "name_employer": "name_employer"}.get(
        reason or "", "email_name_conflict"
    )
    candidates = []
    for donor in db.scalars(
        select(Donor)
        .where(Donor.id.in_(review.candidate_donor_ids), Donor.deleted_at.is_(None))
        .order_by(Donor.id)
    ):
        owner = db.get(User, donor.owner_user_id) if donor.owner_user_id else None
        candidates.append(
            {
                "donor_id": donor.id,
                "display_name": donor.display_name,
                "match_reason": match_reason,
                "owner": {
                    "id": owner.id,
                    "display_name": owner.display_name,
                    "is_active": owner.is_active,
                }
                if owner
                else None,
            }
        )
    decider = db.get(User, review.decided_by) if review.decided_by else None
    return {
        "id": review.id,
        "status": review.status,
        "incoming": {k: v for k, v in review.incoming.items() if not k.startswith("_")},
        "candidates": candidates,
        "file": batch.filename if batch else None,
        "row_number": row.row_number if row else None,
        "decided_by": {
            "id": decider.id,
            "display_name": decider.display_name,
            "is_active": decider.is_active,
        }
        if decider
        else None,
        "decided_at": review.decided_at,
    }


def apply_decision(
    db: Session,
    actor: Actor,
    review: MatchReview,
    decision: str,
    donor: Donor | None,
    incoming: IncomingDonor,
    at: datetime,
    cutoff: date,
) -> None:
    require(actor)
    if review.status != "open":
        raise Conflict("This review was already decided.")
    row = db.get(ImportRow, review.import_row_id) if review.import_row_id else None
    batch = db.get(ImportBatch, row.batch_id) if row else None
    if batch is not None and batch.status != "committed":
        raise Conflict("This import batch is no longer committed.")
    ids = set(review.incoming.get("_gift_ids", []))
    if review.gift_id is not None:
        ids.add(review.gift_id)
    gifts = list(
        db.scalars(select(Gift).where(Gift.id.in_(ids)).order_by(Gift.id).with_for_update())
    )
    if len(gifts) != len(ids) or any(
        g.deleted_at or g.attribution != "pending_review" for g in gifts
    ):
        raise Conflict("The pending gifts changed. Reload the review.")
    if batch and any(g.import_batch_id != batch.id for g in gifts):
        raise Conflict("A pending gift no longer belongs to this import batch.")
    for gift in gifts:
        gift.donor_id = donor.id if donor else None
        gift.attribution = "linked" if donor else "anonymous"
        gift.assumed_thanked = gift.assumed_thanked or gift.gift_date < cutoff
    if row:
        row.donor_id = donor.id if donor else None
        if decision == "create_new" and donor:
            row.normalized = (row.normalized or {}) | {"_created_donor_id": donor.id}
    if donor:
        learn(db, actor, donor, incoming, batch.source if batch else "review", at=at)
    review.incoming = review.incoming | {
        "_fingerprint": fingerprint(incoming),
        "_fingerprints": fingerprints(incoming),
        "_resolved_donor_id": donor.id if donor else None,
    }
    review.status = {"link": "linked", "create_new": "created_new", "anonymous": "anonymous"}[
        decision
    ]
    review.decided_by, review.decided_at = actor.user_id, at
    audit.write(
        db,
        actor,
        "review.decide",
        entity="match_review",
        entity_id=review.id,
        data={
            "decision": decision,
            "donor_id": donor.id if donor else None,
            "gift_ids": sorted(ids),
        },
        at=at,
    )
    db.flush()
