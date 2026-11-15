"""Super admin nominations (GOV-2, D-144): nominate, confirm by a different member, cancel.

Only while the org is flat. Nominations expire 72 hours after creation; expiry is applied when
a nomination is read, so no background job is needed.
"""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.clock import Clock
from app.db.models import SuperAdminNomination, User
from app.errors import Conflict, Forbidden, NotFound
from app.repos import audit
from app.schemas.common import MemberRef
from app.schemas.members import GovernanceDetail, NominationOut
from app.services.governance import service as governance
from app.services.governance import superadmin

TTL = timedelta(hours=72)


def _member_only(actor: Actor) -> None:
    """Members acting through a session. API keys, even full-access ones, never pass."""
    if actor.kind != "user" or actor.full_access:
        raise Forbidden("Only a signed-in member can do this, not an API key.")


def _require(actor: Actor, action: Action) -> None:
    _member_only(actor)
    if not can(actor, action):  # for a member the only denial is "a super admin is active"
        raise Conflict("The organization already has a super admin.")


def _expire_stale(db: Session, clock: Clock) -> None:
    db.execute(
        update(SuperAdminNomination)
        .where(
            SuperAdminNomination.status == "pending",
            SuperAdminNomination.expires_at <= clock.now(),
        )
        .values(status="expired", decided_at=SuperAdminNomination.expires_at)
        .execution_options(synchronize_session="fetch")
    )


def _ref(db: Session, user_id: int) -> MemberRef:
    u = db.get(User, user_id)
    assert u is not None  # the foreign key guarantees it
    return MemberRef(id=u.id, display_name=u.display_name, is_active=u.is_active)


def _out(db: Session, n: SuperAdminNomination) -> NominationOut:
    return NominationOut(
        id=n.id,
        nominee=_ref(db, n.nominee_user_id),
        nominated_by=_ref(db, n.nominated_by),
        status=n.status,
        created_at=n.created_at,
        expires_at=n.expires_at,
    )


def _pending_row(db: Session) -> SuperAdminNomination | None:
    return db.execute(
        select(SuperAdminNomination).where(SuperAdminNomination.status == "pending")
    ).scalar_one_or_none()


def _get_pending(db: Session, clock: Clock, nomination_id: int) -> SuperAdminNomination:
    _expire_stale(db, clock)
    n = db.get(SuperAdminNomination, nomination_id)
    if n is None:
        raise NotFound("No such nomination.")
    db.refresh(n)  # the bulk update above may have changed it
    if n.status != "pending":
        raise Conflict(f"This nomination is {n.status}.")
    return n


def pending(db: Session, clock: Clock, actor: Actor) -> NominationOut | None:
    _member_only(actor)
    _expire_stale(db, clock)
    n = _pending_row(db)
    return _out(db, n) if n else None


def nominate(db: Session, clock: Clock, actor: Actor, nominee_id: int) -> NominationOut:
    _require(actor, Action.GOV_NOMINATE)
    _expire_stale(db, clock)
    nominee = db.get(User, nominee_id)
    if nominee is None:
        raise NotFound("No such member.")
    if not nominee.is_active:
        raise Conflict("That member is deactivated.")
    busy = Conflict("A nomination is already pending. Confirm or cancel it first.")
    if _pending_row(db) is not None:
        raise busy
    now = clock.now()
    n = SuperAdminNomination(
        nominee_user_id=nominee.id, nominated_by=actor.id, created_at=now, expires_at=now + TTL
    )
    try:
        with db.begin_nested():  # the partial unique index settles a race between two requests
            db.add(n)
            db.flush()
    except IntegrityError as exc:
        raise busy from exc
    audit.write(
        db, actor, "gov.nomination_created", entity="super_admin_nomination", entity_id=n.id,
        data={"nominee_user_id": nominee.id}, at=now,
    )  # fmt: skip
    return _out(db, n)


def confirm(db: Session, clock: Clock, actor: Actor, nomination_id: int) -> GovernanceDetail:
    _require(actor, Action.GOV_CONFIRM_NOMINATION)
    n = _get_pending(db, clock, nomination_id)
    if actor.id == n.nominated_by:
        raise Forbidden("A different member must confirm. You made this nomination.")
    nominee = db.get(User, n.nominee_user_id)
    if nominee is None or not nominee.is_active:
        raise Conflict("The nominee is deactivated. Cancel this nomination.")
    now = clock.now()
    superadmin.grant(db, actor, clock, nominee)
    n.status, n.confirmed_by, n.decided_at = "confirmed", actor.id, now
    audit.write(
        db, actor, "gov.nomination_confirmed", entity="super_admin_nomination", entity_id=n.id,
        data={"nominee_user_id": nominee.id, "nominated_by": n.nominated_by}, at=now,
    )  # fmt: skip
    db.flush()
    return governance.get(db, actor)


def cancel(db: Session, clock: Clock, actor: Actor, nomination_id: int) -> NominationOut:
    _member_only(actor)
    n = _get_pending(db, clock, nomination_id)
    if actor.id not in (n.nominated_by, n.nominee_user_id):
        raise Forbidden("Only the nominator or the nominee can cancel this nomination.")
    n.status, n.decided_at = "cancelled", clock.now()
    audit.write(
        db, actor, "gov.nomination_cancelled", entity="super_admin_nomination", entity_id=n.id,
        data={"nominee_user_id": n.nominee_user_id}, at=n.decided_at,
    )  # fmt: skip
    db.flush()
    return _out(db, n)
