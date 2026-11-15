"""Create, edit and delete donors by hand (DON-7, DED-6, DON-11)."""

from typing import Any

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.errors import Invalid
from app.repos import donor_writes as repo
from app.schemas.common import ErrorDetail, MemberRef
from app.schemas.donors import (
    DonorCreate,
    DonorDetail,
    DonorUpdate,
    DuplicateCandidate,
    PossibleDuplicateOut,
)
from app.services.donors import service
from app.services.ingest import normalizers
from app.services.ingest.adapters import IncomingDonor

POSSIBLE_DUPLICATE = (
    "This looks like someone already in CIC Compass. Check the matches, or send "
    "confirm_new to add them anyway."
)


def _contact(email: str | None, phone: str | None) -> tuple[str | None, str | None]:
    """Emails are stored lower case; phones as E.164 when they parse (DATA_MODEL 2.2)."""
    clean_phone = normalizers.phone(phone) if phone else None
    if phone and not clean_phone:
        raise Invalid("Phone number needs at least one digit.")
    return (normalizers.email(email) or None) if email else None, clean_phone


def create_donor(
    db: Session, clock: Clock, actor: Actor, body: DonorCreate
) -> DonorDetail | PossibleDuplicateOut:
    email, phone = _contact(body.email, body.phone)
    incoming = IncomingDonor(
        kind=body.kind,
        display_name=body.display_name,
        first_name=body.first_name or "",
        last_name=body.last_name or "",
        organization=body.organization or "",
        email=email or "",
        phone=phone or "",
        notes=body.notes or "",
    )
    if not body.confirm_new:
        found = repo.duplicates(db, actor, incoming)
        if found:
            return PossibleDuplicateOut(
                error=ErrorDetail(code="possible_duplicate", message=POSSIBLE_DUPLICATE),
                candidates=[
                    DuplicateCandidate(
                        donor_id=r["donor_id"],
                        display_name=r["display_name"],
                        owner=MemberRef(
                            id=r["owner_user_id"],
                            display_name=r["owner_name"],
                            is_active=r["owner_active"],
                        )
                        if r["owner_user_id"] is not None
                        else None,
                        match_reason=r["reason"],
                    )
                    for r in found
                ],
            )
    donor = repo.create(
        db,
        actor,
        incoming,
        {
            "kind": body.kind,
            "display_name": body.display_name,
            "first_name": body.first_name,
            "last_name": body.last_name,
            "organization": body.organization,
            "email": email,
            "phone": phone,
            "do_not_contact": body.do_not_contact,
            "notes": body.notes,
        },
        clock.now(),
    )
    return service.get_donor(db, clock, actor, donor.id)


def update_donor(
    db: Session, clock: Clock, actor: Actor, donor_id: int, body: DonorUpdate
) -> DonorDetail:
    changes: dict[str, Any] = body.model_dump(exclude_unset=True)
    if not changes:
        raise Invalid("Send at least one field to change.")
    for required in ("display_name", "do_not_contact"):
        if required in changes and changes[required] is None:
            raise Invalid(f"{required} cannot be cleared.")
    if "email" in changes or "phone" in changes:
        email, phone = _contact(changes.get("email"), changes.get("phone"))
        if "email" in changes:
            changes["email"] = email
        if "phone" in changes:
            changes["phone"] = phone
    repo.update(db, actor, donor_id, changes, clock.now())
    return service.get_donor(db, clock, actor, donor_id)


def delete_donor(db: Session, clock: Clock, actor: Actor, donor_id: int) -> None:
    repo.soft_delete(db, actor, donor_id, clock.now())
