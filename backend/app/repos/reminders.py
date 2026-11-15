"""Derived reminders (REM-1 to REM-4, D-108): queries over existing rows, never stored.

Every function takes `today` from the injected clock. Doing the action clears the reminder
because the rows it writes (a sent message, an `interactions` row, a done next step) change the
query result. Employer matches never create thank-you reminders (D-127)."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import AppSetting
from app.errors import Forbidden

DEFAULTS = {
    "thank_you_days_first": 2,
    "thank_you_days_repeat": 7,
    "quarterly_days": 90,
}
THANK_YOU_WINDOW = 2  # shown when due <= today + 2
NEXT_STEP_WINDOW = 3  # shown when due <= today + 3


@dataclass(frozen=True)
class Row:
    type: str
    donor_id: int
    donor_name: str
    owner_user_id: int | None
    owner_name: str | None
    owner_active: bool
    due_date: date | None
    gift_id: int | None = None
    next_step_id: int | None = None


class _Owned:
    owner_user_id: int | None = None


def _require_member(actor: Actor) -> None:
    if not can(actor, Action.DONOR_VIEW, _Owned()):
        raise Forbidden("Sign in to see reminders.")


def _setting(db: Session, key: str) -> int:
    row = db.get(AppSetting, key)
    return int(row.value) if row else DEFAULTS[key]


_SELECT = (
    "SELECT d.id AS donor_id, d.display_name AS donor_name, d.owner_user_id, "
    "u.display_name AS owner_name, COALESCE(u.is_active, TRUE) AS owner_active"
)
_LIVE_DONOR = "d.deleted_at IS NULL AND d.merged_into_id IS NULL"
_OWNER_JOIN = "LEFT JOIN users u ON u.id = d.owner_user_id"
_OWNER_FILTER = "(CAST(:owner AS bigint) IS NULL OR d.owner_user_id = :owner)"


def _rows(db: Session, kind: str, sql: str, params: dict[str, Any]) -> list[Row]:
    return [
        Row(type=kind, **{k: v for k, v in r.items() if k in Row.__dataclass_fields__})
        for r in db.execute(text(sql), params).mappings()
    ]


def thank_you_due(db: Session, actor: Actor, *, today: date, owner: int | None = None) -> list[Row]:
    _require_member(actor)
    days = "CASE WHEN f.id = g.id THEN CAST(:first AS integer) ELSE CAST(:repeat AS integer) END"
    sql = f"""
        WITH first_gift AS (
          SELECT DISTINCT ON (donor_id) donor_id, id FROM gifts
          WHERE attribution = 'linked' AND deleted_at IS NULL AND NOT is_matching_gift
          ORDER BY donor_id, gift_date, id)
        {_SELECT}, g.id AS gift_id, g.gift_date + {days} AS due_date
        FROM gifts g
        JOIN donors d ON d.id = g.donor_id
        {_OWNER_JOIN}
        JOIN first_gift f ON f.donor_id = g.donor_id
        WHERE g.attribution = 'linked' AND g.deleted_at IS NULL
          AND NOT g.assumed_thanked AND NOT g.is_matching_gift
          AND {_LIVE_DONOR} AND NOT d.do_not_contact
          AND {_OWNER_FILTER}
          AND g.gift_date + {days} <= CAST(:today AS date) + {THANK_YOU_WINDOW}
          AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.gift_id = g.id
                          AND m.status IN ('sent', 'sent_manually'))
          AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.gift_id = g.id
                          AND i.kind = 'thank_you')
        ORDER BY due_date, g.id
    """  # noqa: S608
    params = {
        "today": today,
        "owner": owner,
        "first": _setting(db, "thank_you_days_first"),
        "repeat": _setting(db, "thank_you_days_repeat"),
    }
    return _rows(db, "thank_you_due", sql, params)


def quarterly_due(db: Session, actor: Actor, *, today: date, owner: int | None = None) -> list[Row]:
    """No sent message and no logged contact for more than `quarterly_days` (REM-2)."""
    _require_member(actor)
    sql = f"""
        {_SELECT}, t.last_touch + CAST(:days AS integer) AS due_date
        FROM donors d
        {_OWNER_JOIN}
        CROSS JOIN LATERAL (SELECT greatest(
            (d.created_at AT TIME ZONE 'America/Phoenix')::date,
            (SELECT max((m.sent_at AT TIME ZONE 'America/Phoenix')::date) FROM messages m
              WHERE m.donor_id = d.id AND m.status IN ('sent', 'sent_manually')),
            (SELECT max(i.occurred_on) FROM interactions i
              WHERE i.donor_id = d.id AND i.kind <> 'system')
        ) AS last_touch) t
        WHERE {_LIVE_DONOR} AND NOT d.do_not_contact
          AND {_OWNER_FILTER}
          AND t.last_touch < CAST(:today AS date) - CAST(:days AS integer)
        ORDER BY due_date, d.id
    """  # noqa: S608
    params = {"today": today, "owner": owner, "days": _setting(db, "quarterly_days")}
    return _rows(db, "quarterly_due", sql, params)


def next_step_due(db: Session, actor: Actor, *, today: date, owner: int | None = None) -> list[Row]:
    _require_member(actor)
    sql = f"""
        {_SELECT}, s.id AS next_step_id, s.due_date
        FROM next_steps s
        JOIN donors d ON d.id = s.donor_id
        {_OWNER_JOIN}
        WHERE s.status = 'open' AND {_LIVE_DONOR}
          AND {_OWNER_FILTER}
          AND s.due_date <= CAST(:today AS date) + {NEXT_STEP_WINDOW}
        ORDER BY s.due_date, s.id
    """
    return _rows(db, "next_step_due", sql, {"today": today, "owner": owner})


def needs_reassignment(db: Session, actor: Actor) -> list[Row]:
    """Donors whose owner is deactivated (OWN-5). Shown to every member."""
    _require_member(actor)
    sql = f"""
        {_SELECT}, NULL::date AS due_date
        FROM donors d
        JOIN users u ON u.id = d.owner_user_id
        WHERE NOT u.is_active AND {_LIVE_DONOR}
        ORDER BY lower(d.display_name), d.id
    """
    return _rows(db, "needs_reassignment", sql, {})
