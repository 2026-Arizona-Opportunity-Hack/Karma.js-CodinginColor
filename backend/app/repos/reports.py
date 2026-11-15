"""Aggregate queries for reports and the public API. No donor identifiers leave this module.

Org totals count linked and anonymous gifts (DED-8) and skip gifts waiting for review (DED-5).
Callers must be a member, the setup CLI or an API key; anything else is refused.
"""

from datetime import date
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.errors import Forbidden

Period = Literal["month", "quarter", "year"]
_COUNTED = "g.deleted_at IS NULL AND g.attribution IN ('linked','anonymous')"


def _require_reader(actor: Actor) -> None:
    if actor.kind not in ("user", "api_key", "cli"):
        raise Forbidden("Not allowed to read reports.")


def _rows(db: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def by_period(
    db: Session, actor: Actor, *, start: date, end: date, period: Period
) -> list[dict[str, Any]]:
    _require_reader(actor)
    return _rows(
        db,
        f"""
        SELECT date_trunc(:period, g.gift_date)::date AS period_start,
               COALESCE(sum(g.gross_cents), 0)::bigint AS gross_cents,
               COALESCE(sum(g.net_cents), 0)::bigint AS net_cents,
               count(*)::int AS gift_count,
               count(DISTINCT g.donor_id)::int AS donor_count
        FROM gifts g
        WHERE {_COUNTED} AND g.gift_date BETWEEN :start AND :end
        GROUP BY 1 ORDER BY 1
        """,  # noqa: S608 - the only interpolation is a constant
        period=period,
        start=start,
        end=end,
    )


def by_program(db: Session, actor: Actor, *, start: date, end: date) -> list[dict[str, Any]]:
    _require_reader(actor)
    return _rows(
        db,
        f"""
        SELECT p.name AS program,
               COALESCE(sum(g.gross_cents), 0)::bigint AS gross_cents,
               count(*)::int AS gift_count,
               count(DISTINCT g.donor_id)::int AS donor_count
        FROM gifts g JOIN programs p ON p.id = g.program_id
        WHERE {_COUNTED} AND g.gift_date BETWEEN :start AND :end
        GROUP BY p.name ORDER BY gross_cents DESC, p.name
        """,  # noqa: S608
        start=start,
        end=end,
    )


def by_board_member(db: Session, actor: Actor, *, start: date, end: date) -> list[dict[str, Any]]:
    """Per member: donors they own, giving of those donors, and the work they logged."""
    _require_reader(actor)
    return _rows(
        db,
        """
        SELECT u.display_name AS board_member,
          (SELECT count(*) FROM donors d
             WHERE d.owner_user_id = u.id AND d.deleted_at IS NULL)::int AS donors_owned,
          COALESCE((SELECT sum(g.gross_cents) FROM gifts g JOIN donors d ON d.id = g.donor_id
             WHERE d.owner_user_id = u.id AND d.deleted_at IS NULL AND g.deleted_at IS NULL
               AND g.attribution = 'linked' AND g.gift_date BETWEEN :start AND :end), 0
          )::bigint AS gross_cents,
          (SELECT count(*) FROM interactions i
             WHERE i.user_id = u.id AND i.kind <> 'system'
               AND i.occurred_on BETWEEN :start AND :end)::int AS contacts_logged,
          (SELECT count(*) FROM messages m
             WHERE m.sent_by = u.id AND m.status IN ('sent','sent_manually')
               AND (m.sent_at AT TIME ZONE 'America/Phoenix')::date
                   BETWEEN :start AND :end)::int AS messages_sent
        FROM users u ORDER BY u.display_name, u.id
        """,
        start=start,
        end=end,
    )


def activity_by_day(db: Session, actor: Actor, *, start: date, end: date) -> list[dict[str, Any]]:
    """One row per calendar day from start to end, zeros included."""
    _require_reader(actor)
    return _rows(
        db,
        f"""
        SELECT d::date AS day,
          (SELECT count(*) FROM gifts g WHERE {_COUNTED} AND g.gift_date = d::date)::int
            AS gifts_received,
          COALESCE((SELECT sum(g.gross_cents) FROM gifts g
             WHERE {_COUNTED} AND g.gift_date = d::date), 0)::bigint AS gross_cents,
          (SELECT count(*) FROM interactions i
             WHERE i.kind <> 'system' AND i.occurred_on = d::date)::int AS contacts_logged,
          (SELECT count(*) FROM messages m WHERE m.status IN ('sent','sent_manually')
             AND (m.sent_at AT TIME ZONE 'America/Phoenix')::date = d::date)::int AS messages_sent
        FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') d
        ORDER BY d
        """,  # noqa: S608
        start=start,
        end=end,
    )
