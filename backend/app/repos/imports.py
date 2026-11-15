"""Import database access. Every entry point checks the acting member's policy."""

from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import policy
from app.authz.actor import Actor
from app.clock import PHOENIX
from app.db.models import (
    AppSetting,
    Donor,
    DonorIdentity,
    Gift,
    ImportBatch,
    ImportRow,
    MatchReview,
    Program,
    SourceProgramMap,
    User,
)
from app.errors import Conflict, Forbidden, Invalid, NotFound
from app.repos import audit
from app.schemas.common import DonorKind, ImportSource, MemberRef
from app.services.ingest.adapters import IncomingDonor
from app.services.ingest.preview import PlannedGift, PlannedRow, PreviewState, Snapshot


def require(actor: Actor) -> None:
    if not policy.can(actor, "import.run"):
        raise Forbidden("You cannot run imports.")


def check_file(db: Session, actor: Actor, source: ImportSource, file_sha256: str) -> None:
    require(actor)
    found = db.execute(
        select(ImportBatch, User)
        .join(User, User.id == ImportBatch.uploaded_by)
        .where(
            ImportBatch.source == source,
            ImportBatch.file_sha256 == file_sha256,
            ImportBatch.status == "committed",
        )
    ).first()
    if found:
        batch, member = found
        at = batch.committed_at or batch.created_at
        raise Conflict(
            f"Already imported on {at.astimezone(PHOENIX).date()} by {member.display_name}."
        )


def snapshot(
    db: Session, actor: Actor, source: ImportSource, data: bytes, *, file_sha256: str | None = None
) -> Snapshot:
    require(actor)
    check_file(db, actor, source, file_sha256 or sha256(data).hexdigest())
    member = db.get(User, actor.user_id) if actor.user_id is not None else None
    if member is None or not member.is_active:
        raise Forbidden("An active board member must run the import.")
    general = db.scalar(select(Program.id).where(Program.slug == "general"))
    if general is None:
        raise Invalid("The General program is missing.")
    setting = db.get(AppSetting, "import_cutoff_days")
    cutoff = int(setting.value) if setting else 60
    if cutoff < 0:
        raise Invalid("Import cutoff must not be negative.")
    out = Snapshot(
        member=MemberRef(id=member.id, display_name=member.display_name),
        general_program=general,
        cutoff_days=cutoff,
    )
    out.row_keys = set(db.scalars(select(Gift.row_key).where(Gift.deleted_at.is_(None))))
    out.programs = {
        mapping.source_value_norm.strip().lower(): mapping.program_id
        for mapping in db.scalars(select(SourceProgramMap).where(SourceProgramMap.source == source))
    }
    for donor in db.scalars(select(Donor).where(Donor.deleted_at.is_(None)).order_by(Donor.id)):
        kind: DonorKind = "person"
        if donor.kind == "organization":
            kind = "organization"
        elif donor.kind == "funder":
            kind = "funder"
        first, _, last = donor.display_name.rpartition(" ")
        out.donors[donor.id] = IncomingDonor(
            kind=kind,
            display_name=donor.display_name,
            first_name=donor.first_name or first or last,
            last_name=donor.last_name or (last if first else ""),
            organization=donor.organization or "",
            email=donor.email or "",
            phone=donor.phone or "",
        )
    out.identities = [
        (identity.donor_id, identity.kind, identity.value_norm)
        for identity in db.scalars(select(DonorIdentity).order_by(DonorIdentity.id))
        if identity.donor_id in out.donors
    ]
    for review in db.scalars(
        select(MatchReview)
        .where(MatchReview.status != "open")
        .order_by(MatchReview.decided_at, MatchReview.id)
    ):
        did = review.incoming.get("_resolved_donor_id")
        keys = review.incoming.get("_fingerprints", [review.incoming.get("_fingerprint")])
        for key in keys:
            if key and (did is None or did in out.donors):
                out.remembered[key] = did
    return out


def find_batch(
    db: Session, actor: Actor, batch_id: int, *, lock: bool = False
) -> ImportBatch | None:
    require(actor)
    query = select(ImportBatch).where(ImportBatch.id == batch_id)
    return db.scalar(query.with_for_update() if lock else query)


def list_batches(db: Session, actor: Actor) -> list[ImportBatch]:
    require(actor)
    return list(
        db.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc(), ImportBatch.id))
    )


def batch_output(db: Session, actor: Actor, batch: ImportBatch) -> dict[str, Any]:
    require(actor)
    user = db.get(User, batch.uploaded_by)
    if user is None:
        raise NotFound("Import uploader not found.")
    return {
        "id": batch.id,
        "source": batch.source,
        "filename": batch.filename,
        "status": batch.status,
        "uploaded_by": {
            "id": user.id,
            "display_name": user.display_name,
            "is_active": user.is_active,
        },
        "created_at": batch.created_at,
        "committed_at": batch.committed_at,
        "reversed_at": batch.reversed_at,
        "cutoff_date": batch.cutoff_date,
        "summary": batch.summary,
    }


def save_batch(db: Session, actor: Actor, state: PreviewState, at: datetime) -> ImportBatch:
    require(actor)
    incoming = state.output.batch
    batch = ImportBatch(
        id=incoming.id,
        source=incoming.source,
        filename=incoming.filename,
        file_sha256=state.file_sha256,
        uploaded_by=incoming.uploaded_by.id,
        created_at=incoming.created_at,
        committed_at=at,
        status="committed",
        cutoff_date=incoming.cutoff_date,
        summary=state.output.summary.model_dump(mode="json"),
    )
    db.add(batch)
    db.flush()
    return batch


def update_profile(
    db: Session, actor: Actor, donor: Donor, incoming: IncomingDonor, at: datetime
) -> None:
    require(actor)
    donor.kind, donor.display_name = incoming.kind, incoming.display_name
    for key in ("first_name", "last_name", "organization", "email", "phone", "notes"):
        if value := getattr(incoming, key):
            setattr(donor, key, value)
    donor.updated_at = at


def save_gifts(
    db: Session,
    actor: Actor,
    batch: ImportBatch,
    row: PlannedRow,
    donor_id: int | None,
    at: datetime,
) -> list[Gift]:
    require(actor)
    attribution = (
        "pending_review"
        if row.status == "needs_review"
        else ("linked" if donor_id is not None else "anonymous")
    )

    def gift_model(planned: PlannedGift) -> Gift:
        gift = planned.gift
        return Gift(
            donor_id=donor_id,
            attribution=attribution,
            source=batch.source,
            source_platform=gift.source_platform or None,
            source_txn_id=gift.source_txn_id or None,
            row_key=planned.row_key,
            gift_date=gift.gift_date,
            gross_cents=gift.gross_cents,
            fee_cents=gift.fee_cents,
            net_cents=gift.net_cents,
            currency="USD",
            program_id=planned.program_id,
            campaign_name=gift.campaign_name or None,
            is_matching_gift=gift.is_matching_gift,
            payer_name=gift.payer_name or None,
            assumed_thanked=planned.assumed_thanked,
            import_batch_id=batch.id,
            created_at=at,
        )

    gifts = [gift_model(gift) for gift in row.gifts if not gift.already_imported]
    db.add_all(gifts)
    if gifts:
        db.flush()
    return gifts


def save_row(
    db: Session,
    actor: Actor,
    batch: ImportBatch,
    plan: PlannedRow,
    donor_id: int | None,
    gifts: list[Gift],
) -> ImportRow:
    require(actor)
    status: str = plan.status
    if batch.source == "spreadsheet":
        status = {"new": "donor_new", "already_imported": "donor_matched"}.get(status, status)
    row = ImportRow(
        batch_id=batch.id,
        row_number=plan.incoming.row_number,
        status=status,
        reason=plan.reason,
        normalized=plan.model_dump(mode="json"),
        donor_id=donor_id,
        row_key=plan.gifts[0].row_key if plan.gifts else None,
        gift_id=gifts[0].id if gifts else None,
    )
    db.add(row)
    db.flush()
    return row


def save_review(
    db: Session,
    actor: Actor,
    row: ImportRow,
    plan: PlannedRow,
    gift_ids: list[int],
    candidates: list[int],
) -> None:
    require(actor)
    db.add(
        MatchReview(
            import_row_id=row.id,
            gift_id=gift_ids[0] if gift_ids else None,
            incoming=plan.incoming.donor.model_dump(mode="json")
            | {
                "_gift_ids": gift_ids,
                "_reason": plan.reason,
            },
            candidate_donor_ids=candidates,
        )
    )
    db.flush()


def finish(
    db: Session,
    actor: Actor,
    batch: ImportBatch,
    *,
    created_ids: list[int],
    inserted_gifts: int,
    disbursements: dict[str, int],
    at: datetime,
) -> None:
    require(actor)
    batch.summary = (batch.summary or {}) | {
        "new_donor_ids": created_ids,
        "inserted_gifts": inserted_gifts,
        "disbursements": disbursements,
    }
    audit.write(
        db,
        actor,
        "import.commit",
        entity="import_batch",
        entity_id=batch.id,
        data={
            "source": batch.source,
            "new_donors": len(created_ids),
            "inserted_gifts": inserted_gifts,
            "rows": batch.summary["rows_read"],
        },
        at=at,
    )
    db.flush()


def reverse(db: Session, actor: Actor, batch: ImportBatch, at: datetime) -> None:
    require(actor)
    if batch.status != "committed":
        raise Conflict("Only a committed batch can be reversed.")
    gifts = list(
        db.scalars(select(Gift).where(Gift.import_batch_id == batch.id, Gift.deleted_at.is_(None)))
    )
    for gift in gifts:
        gift.deleted_at = at
    db.flush()
    rows = list(db.scalars(select(ImportRow).where(ImportRow.batch_id == batch.id)))
    created = set((batch.summary or {}).get("new_donor_ids", []))
    created.update(
        row.normalized["_created_donor_id"]
        for row in rows
        if row.normalized and row.normalized.get("_created_donor_id")
    )
    removed = []
    for donor_id in sorted(created):
        donor = db.get(Donor, donor_id)
        remaining = db.scalar(
            select(Gift.id).where(Gift.donor_id == donor_id, Gift.deleted_at.is_(None)).limit(1)
        )
        if donor and donor.deleted_at is None and remaining is None:
            donor.deleted_at = at
            removed.append(donor_id)
    for review in db.scalars(
        select(MatchReview)
        .join(ImportRow, ImportRow.id == MatchReview.import_row_id)
        .where(ImportRow.batch_id == batch.id, MatchReview.status == "open")
    ):
        review.status, review.decided_by, review.decided_at = "anonymous", actor.user_id, at
        review.incoming = review.incoming | {"import_reversed": True}
        audit.write(
            db,
            actor,
            "review.reverse",
            entity="match_review",
            entity_id=review.id,
            data={"batch_id": batch.id},
            at=at,
        )
    batch.status, batch.reversed_at = "reversed", at
    audit.write(
        db,
        actor,
        "import.reverse",
        entity="import_batch",
        entity_id=batch.id,
        data={"gifts": len(gifts), "soft_deleted_donors": removed},
        at=at,
    )
    db.flush()
