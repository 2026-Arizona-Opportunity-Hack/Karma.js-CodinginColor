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
               count(DISTINCT g.donor_id) FILTER (WHERE NOT g.is_matching_gift)::int AS donor_count
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
               count(DISTINCT g.donor_id) FILTER (WHERE NOT g.is_matching_gift)::int AS donor_count
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
        SELECT u.id AS member_id, u.display_name AS board_member, u.is_active,
          (SELECT count(*) FROM donors d
             WHERE d.owner_user_id = u.id AND d.deleted_at IS NULL)::int AS donors_owned,
          COALESCE((SELECT sum(g.gross_cents) FROM gifts g JOIN donors d ON d.id = g.donor_id
             WHERE d.owner_user_id = u.id AND d.deleted_at IS NULL AND g.deleted_at IS NULL
               AND g.attribution = 'linked' AND NOT g.is_matching_gift
               AND g.gift_date BETWEEN :start AND :end), 0
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


def totals(db: Session, actor: Actor, *, start: date, end: date) -> dict[str, Any]:
    """Headline numbers for a date range. `new_donors` first ever gave inside the range."""
    _require_reader(actor)
    rows = _rows(
        db,
        f"""
        SELECT COALESCE(sum(g.gross_cents), 0)::bigint AS gross_cents,
               COALESCE(sum(g.net_cents), 0)::bigint AS net_cents,
               count(*)::int AS gift_count,
               count(DISTINCT g.donor_id) FILTER (WHERE NOT g.is_matching_gift)::int AS donor_count,
               (SELECT count(*) FROM (
                  SELECT f.donor_id FROM gifts f JOIN donors d ON d.id = f.donor_id
                  WHERE f.attribution = 'linked' AND f.deleted_at IS NULL AND NOT f.is_matching_gift
                    AND d.deleted_at IS NULL AND d.merged_into_id IS NULL
                  GROUP BY f.donor_id HAVING min(f.gift_date) BETWEEN :start AND :end
               ) first_gifts)::int AS new_donors
        FROM gifts g WHERE {_COUNTED} AND g.gift_date BETWEEN :start AND :end
        """,  # noqa: S608
        start=start,
        end=end,
    )
    row = rows[0]
    count = row["gift_count"]
    # Average gift in whole cents, half up.
    row["avg_gift_cents"] = (2 * row["gross_cents"] + count) // (2 * count) if count else 0
    return row


def unattributed_count(db: Session, actor: Actor) -> int:
    _require_reader(actor)
    sql = (
        "SELECT count(*) FROM gifts WHERE deleted_at IS NULL "
        "AND attribution IN ('anonymous','pending_review')"
    )
    return int(db.execute(text(sql)).scalar_one())


def retention_donors(
    db: Session,
    actor: Actor,
    *,
    cur: tuple[date, date],
    prev: tuple[date, date],
    before: date,
) -> list[dict[str, Any]]:
    """Per donor with linked gifts: cents in the current and previous window (inclusive dates),
    and whether they gave on or before `before - 1 day` (DATA_MODEL 3.5)."""
    _require_reader(actor)
    return _rows(
        db,
        """
        SELECT d.id AS donor_id, d.display_name,
               COALESCE(sum(g.gross_cents) FILTER (
                 WHERE g.gift_date BETWEEN :cur_start AND :cur_end), 0)::bigint AS cents_cur,
               COALESCE(sum(g.gross_cents) FILTER (
                 WHERE g.gift_date BETWEEN :prev_start AND :prev_end), 0)::bigint AS cents_prev,
               COALESCE(bool_or(g.gift_date < :before), false) AS ever_before
        FROM gifts g JOIN donors d ON d.id = g.donor_id
        WHERE g.attribution = 'linked' AND g.deleted_at IS NULL AND NOT g.is_matching_gift
          AND d.deleted_at IS NULL AND d.merged_into_id IS NULL
        GROUP BY d.id, d.display_name
        ORDER BY lower(d.display_name), d.id
        """,
        cur_start=cur[0],
        cur_end=cur[1],
        prev_start=prev[0],
        prev_end=prev[1],
        before=before,
    )
