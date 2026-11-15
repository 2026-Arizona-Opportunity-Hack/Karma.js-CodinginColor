"""Turn donor rows into API models. Contact fields are removed unless the policy allows them."""

from typing import Any

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.clock import Clock, today
from app.repos import donors as repo
from app.schemas.common import DonorStatus, MemberRef
from app.schemas.donors import (
    DonorCard,
    DonorDetail,
    DonorPage,
    GiftListOut,
    GiftOut,
    TimelineEntry,
    TimelineOut,
)


def statuses(row: dict[str, Any]) -> list[DonorStatus]:
    # thank_you_due and update_due come from the reminders service (lane A, Phase 3).
    out: list[DonorStatus] = []
    if row["is_new"]:
        out.append("new")
    if row["is_lapsed"]:
        out.append("lapsed")
    if row["owner_user_id"] is not None and not row["owner_active"]:
        out.append("owner_inactive")
    if row["do_not_contact"]:
        out.append("do_not_contact")
    return out


def _gift(r: dict[str, Any]) -> GiftOut:
    return GiftOut(**{k: v for k, v in r.items() if k != "rn"})


def _card_fields(row: dict[str, Any], gifts: list[dict[str, Any]]) -> dict[str, Any]:
    owner = (
        MemberRef(
            id=row["owner_user_id"], display_name=row["owner_name"], is_active=row["owner_active"]
        )
        if row["owner_user_id"] is not None
        else None
    )
    return {
        "id": row["id"],
        "kind": row["kind"],
        "display_name": row["display_name"],
        "organization": row["organization"],
        "owner": owner,
        "total_12m_cents": row["total_12m_cents"],
        "total_lifetime_cents": row["total_lifetime_cents"],
        "last_gift_date": row["last_gift_date"],
        "last_contact_date": row["last_contact_date"],
        "next_step_title": row["next_step_title"],
        "next_step_due": row["next_step_due"],
        "statuses": statuses(row),
        "recent_gifts": [_gift(g) for g in gifts],
    }


def list_donors(
    db: Session,
    clock: Clock,
    actor: Actor,
    *,
    scope: str,
    q: str | None,
    owner: int | None,
    status: str | None,
    program: int | None,
    page: int,
    page_size: int,
) -> DonorPage:
    rows, total = repo.list_cards(
        db, actor, today=today(clock), scope=scope, q=q.strip() if q else None, owner=owner,
        status=status, program=program, page=page, page_size=page_size,
    )  # fmt: skip
    gifts = repo.recent_gifts(db, actor, [r["id"] for r in rows])
    return DonorPage(
        items=[DonorCard(**_card_fields(r, gifts[r["id"]])) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_donor(db: Session, clock: Clock, actor: Actor, donor_id: int) -> DonorDetail:
    row = repo.get_card(db, actor, donor_id, today=today(clock))
    gifts = repo.recent_gifts(db, actor, [donor_id])[donor_id]
    owned = repo.OwnedBy(row["owner_user_id"])
    visible = can(actor, Action.DONOR_VIEW_CONTACT, owned)
    return DonorDetail(
        **_card_fields(row, gifts),
        first_name=row["first_name"],
        last_name=row["last_name"],
        # Contact details and free-text notes stay with the owner and an active super admin.
        email=row["email"] if visible else None,
        phone=row["phone"] if visible else None,
        notes=row["notes"] if visible else None,
        contact_visible=visible,
        contact_via=None if visible else row["owner_name"],
        do_not_contact=row["do_not_contact"],
        can_act=can(actor, Action.DONOR_ACT, owned),
        can_reassign=can(actor, Action.DONOR_REASSIGN, owned),
        created_at=row["created_at"],
    )


def get_timeline(db: Session, clock: Clock, actor: Actor, donor_id: int) -> TimelineOut:
    repo.get_card(db, actor, donor_id, today=today(clock))  # 404 for a missing donor
    return TimelineOut(items=[TimelineEntry(**r) for r in repo.timeline(db, actor, donor_id)])


def unattributed(db: Session, actor: Actor) -> GiftListOut:
    return GiftListOut(items=[_gift(r) for r in repo.unattributed_gifts(db, actor)])
