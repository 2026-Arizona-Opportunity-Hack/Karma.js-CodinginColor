"""Import database access. Every entry point checks the acting member's policy."""

from hashlib import sha256

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
    MatchReview,
    Program,
    SourceProgramMap,
    User,
)
from app.errors import Conflict, Forbidden, Invalid
from app.schemas.common import DonorKind, ImportSource, MemberRef
from app.services.ingest.adapters import IncomingDonor
from app.services.ingest.preview import Snapshot


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


def snapshot(db: Session, actor: Actor, source: ImportSource, data: bytes) -> Snapshot:
    require(actor)
    check_file(db, actor, source, sha256(data).hexdigest())
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
