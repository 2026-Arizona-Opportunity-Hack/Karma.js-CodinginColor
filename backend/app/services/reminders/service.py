"""Reminder lists and counts built on the derived queries (REM-1 to REM-5, D-108).

Other lanes import from `app.services.reminders`:
- `todo_for(db, actor, today, user_id)`: one member's reminders, most urgent first, plus
  every needs_reassignment row (the To-do list).
- `counts_by_member(db, actor, today)`: `{user_id: ReminderCounts}` for every active member
  (the digest).
- `quarterly_due_for(db, actor, today, user_id)`: the donors one member owes a quarterly
  touch (draft-quarterly).
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import User
from app.repos import reminders as repo
from app.repos.reminders import Row
from app.schemas.common import MemberRef
from app.schemas.donors import ReminderOut

ACTIONS = {
    "thank_you_due": "draft_thank_you",
    "quarterly_due": "draft_update",
    "next_step_due": "open_next_step",
    "needs_reassignment": "reassign",
}
TYPE_ORDER = {"next_step_due": 0, "thank_you_due": 1, "quarterly_due": 2, "needs_reassignment": 3}


@dataclass(frozen=True)
class ReminderCounts:
    thank_you_due: int = 0
    quarterly_due: int = 0
    next_step_due: int = 0
    needs_reassignment: int = 0


def _out(row: Row, today: date) -> ReminderOut:
    owner = (
        MemberRef(
            id=row.owner_user_id, display_name=row.owner_name or "", is_active=row.owner_active
        )
        if row.owner_user_id is not None
        else None
    )
    return ReminderOut(
        type=row.type,
        donor_id=row.donor_id,
        donor_name=row.donor_name,
        owner=owner,
        due_date=row.due_date,
        overdue=row.due_date is not None and row.due_date < today,
        gift_id=row.gift_id,
        next_step_id=row.next_step_id,
        action=ACTIONS[row.type],
    )


def _urgent_first(rows: list[Row]) -> list[Row]:
    return sorted(rows, key=lambda r: (r.due_date or date.max, TYPE_ORDER[r.type], r.donor_id))


def todo_for(db: Session, actor: Actor, today: date, user_id: int) -> list[ReminderOut]:
    mine = _urgent_first(
        repo.next_step_due(db, actor, today=today, owner=user_id)
        + repo.thank_you_due(db, actor, today=today, owner=user_id)
        + repo.quarterly_due(db, actor, today=today, owner=user_id)
    )
    return [_out(r, today) for r in mine + repo.needs_reassignment(db, actor)]


def needs_reassignment_list(db: Session, actor: Actor, today: date) -> list[ReminderOut]:
    return [_out(r, today) for r in repo.needs_reassignment(db, actor)]


def quarterly_due_for(db: Session, actor: Actor, today: date, user_id: int) -> list[ReminderOut]:
    return [_out(r, today) for r in repo.quarterly_due(db, actor, today=today, owner=user_id)]


def counts_by_member(db: Session, actor: Actor, today: date) -> dict[int, ReminderCounts]:
    """Open reminders per active member. Needs reassignment is the same org-wide number for all."""
    members = list(db.scalars(select(User.id).where(User.is_active.is_(True)).order_by(User.id)))
    orphans = len(repo.needs_reassignment(db, actor))
    by_type = {
        "thank_you_due": repo.thank_you_due(db, actor, today=today),
        "quarterly_due": repo.quarterly_due(db, actor, today=today),
        "next_step_due": repo.next_step_due(db, actor, today=today),
    }
    return {
        uid: ReminderCounts(
            needs_reassignment=orphans,
            **{k: sum(1 for r in rows if r.owner_user_id == uid) for k, rows in by_type.items()},
        )
        for uid in members
    }
