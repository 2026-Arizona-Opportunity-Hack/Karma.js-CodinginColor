"""Manual donor entry: duplicate check, create, edit and soft delete (DED-6, DON-7, DON-11).

Creating a donor takes the same advisory lock as imports (so a duplicate check and the insert
cannot race with an import) and reuses lane A's round-robin and identity memory. Editing and
deleting need `donor.edit` (the owner and an active super admin). Audit entries record which
fields changed, never their values."""

from datetime import date, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import Donor, Gift, Program
from app.errors import Forbidden, Invalid, NotFound
from app.repos import audit, dedupe, ownership
from app.services.dedupe.resolver import identity_keys
from app.services.ingest.adapters import IncomingDonor

MATCH_LIMIT = 5
_REASONS = {"email": ("email", 1), "phone": ("phone", 2), "name_org": ("name_employer", 3)}


def duplicates(db: Session, actor: Actor, incoming: IncomingDonor) -> list[dict[str, Any]]:
    """Active donors that look like `incoming`, best match first (DED-3 keys, DED-6).

    Email beats phone beats name plus employer. A name alone never matches."""
    ownership.lock(db, actor, action="import.run")
    params: dict[str, Any] = {}
    parts: list[str] = []
    for n, (kind, value) in enumerate(identity_keys(incoming)):
        if kind not in _REASONS:
            continue
        reason, rank = _REASONS[kind]
        params[f"v{n}"] = value
        parts.append(
            f"SELECT donor_id AS id, '{reason}' AS reason, {rank} AS rank "  # noqa: S608
            f"FROM donor_identities WHERE kind = '{kind}' AND value_norm = :v{n}"
        )
        # Donors typed in by hand can predate identity rows, so check their own columns too.
        column = {"email": "lower(email::text)", "phone": "phone"}.get(kind)
        if column:
            parts.append(
                f"SELECT id, '{reason}', {rank} FROM donors WHERE {column} = :v{n}"  # noqa: S608
            )
    if not parts:
        return []
    sql = f"""
        SELECT DISTINCT ON (d.id) d.id AS donor_id, d.display_name, d.owner_user_id,
               u.display_name AS owner_name, COALESCE(u.is_active, true) AS owner_active, m.reason
        FROM ({" UNION ALL ".join(parts)}) m
        JOIN donors d ON d.id = m.id AND d.deleted_at IS NULL AND d.merged_into_id IS NULL
        LEFT JOIN users u ON u.id = d.owner_user_id
        ORDER BY d.id, m.rank
    """  # noqa: S608
    rows = [dict(r) for r in db.execute(text(sql), params).mappings()]
    order = {reason: r for reason, r in _REASONS.values()}
    rows.sort(key=lambda r: (order[r["reason"]], r["donor_id"]))
    return rows[:MATCH_LIMIT]


def create(
    db: Session, actor: Actor, incoming: IncomingDonor, fields: dict[str, Any], at: datetime
) -> Donor:
    """Insert the donor, give it an owner by round-robin and remember its identities."""
    ownership.lock(db, actor, action="import.run")
    donor = Donor(**fields, created_via="manual", created_at=at, updated_at=at)
    db.add(donor)
    db.flush()
    ownership.assign(db, actor, donor, at, action="import.run")
    dedupe.learn(db, actor, donor, incoming, "manual", at=at, action="import.run")
    audit.write(
        db, actor, "donor.create", entity="donor", entity_id=donor.id,
        data={"kind": donor.kind, "custom_keys": sorted(donor.custom or {})},
        at=at,
    )  # fmt: skip
    return donor


def _editable(db: Session, actor: Actor, donor_id: int) -> Donor:
    donor = db.execute(
        select(Donor)
        .where(Donor.id == donor_id, Donor.deleted_at.is_(None), Donor.merged_into_id.is_(None))
        .with_for_update()
    ).scalar_one_or_none()
    if donor is None:
        raise NotFound("Donor not found.")
    if not can(actor, Action.DONOR_EDIT, donor):
        raise Forbidden("Only the donor's owner can change this donor.")
    return donor


def _changed_keys(old: dict[str, Any], new: dict[str, Any] | None) -> list[str]:
    """Which custom fields changed. Values are never written to the audit log."""
    new = new or {}
    return sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))


def update(
    db: Session, actor: Actor, donor_id: int, changes: dict[str, Any], at: datetime
) -> tuple[Donor, IncomingDonor]:
    """Apply `changes` and return the donor with its new identity data for the caller to learn."""
    donor = _editable(db, actor, donor_id)
    old_custom = dict(donor.custom or {})
    for name, value in changes.items():
        setattr(donor, name, value)
    donor.updated_at = at
    audit.write(
        db, actor, "donor.update", entity="donor", entity_id=donor.id,
        data={"fields": sorted(changes)}
        | ({"custom_keys": _changed_keys(old_custom, donor.custom)} if "custom" in changes else {}),
        at=at,
    )  # fmt: skip
    db.flush()
    incoming = IncomingDonor(
        kind=donor.kind,
        display_name=donor.display_name,
        first_name=donor.first_name or "",
        last_name=donor.last_name or "",
        organization=donor.organization or "",
        email=donor.email or "",
        phone=donor.phone or "",
    )
    dedupe.learn(db, actor, donor, incoming, "manual", at=at, action="import.run")
    return donor, incoming


def soft_delete(db: Session, actor: Actor, donor_id: int, at: datetime) -> None:
    """Soft delete only: the donor, its gifts and its history stay in the database (DON-11)."""
    donor = _editable(db, actor, donor_id)
    donor.deleted_at, donor.updated_at = at, at
    audit.write(db, actor, "donor.delete", entity="donor", entity_id=donor.id, at=at)
    db.flush()


def add_manual_gift(
    db: Session,
    actor: Actor,
    donor_id: int,
    *,
    gift_date: date,
    gross_cents: int,
    program_id: int | None,
    assumed_thanked: bool,
    at: datetime,
    custom: dict[str, Any] | None = None,
) -> Gift:
    """A gift typed in by hand, for example a check (DON-8). Owner and active super admin only.

    The row key is random so a manual gift never collides with an imported one, and two
    identical checks on the same day stay two gifts."""
    donor = _editable(db, actor, donor_id)
    if program_id is None:
        program = db.scalar(select(Program).where(Program.slug == "general"))
    else:
        program = db.get(Program, program_id)
    if program is None or not program.is_active:
        raise Invalid("Choose an active program.")
    gift = Gift(
        donor_id=donor.id,
        attribution="linked",
        source="manual",
        row_key=sha256(f"v1|manual|{uuid4()}".encode()).hexdigest(),
        gift_date=gift_date,
        gross_cents=gross_cents,
        fee_cents=0,
        net_cents=gross_cents,
        program_id=program.id,
        assumed_thanked=assumed_thanked,
        custom=custom or {},
        created_by=actor.user_id,
    )
    db.add(gift)
    db.flush()
    audit.write(
        db, actor, "gift.create", entity="gift", entity_id=gift.id,
        data={"donor_id": donor.id, "source": "manual", "custom_keys": sorted(custom or {})},
        at=at,
    )  # fmt: skip
    return gift
