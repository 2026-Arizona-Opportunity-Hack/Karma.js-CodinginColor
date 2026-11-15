"""Reads behind the funder export (RPT-3). Gift history is open to every member (D-104)."""

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import Donor
from app.errors import Forbidden, NotFound


def _require_member(actor: Actor) -> None:
    if actor.kind not in ("user", "cli"):
        raise Forbidden("Not allowed to export donor data.")


def donor_for_export(db: Session, actor: Actor, donor_id: int) -> Donor:
    _require_member(actor)
    donor = db.get(Donor, donor_id)
    if donor is None or donor.deleted_at is not None or donor.merged_into_id is not None:
        raise NotFound("Donor not found.")
    return donor


def gift_lines(
    db: Session, actor: Actor, *, donor_id: int, start: date, end: date
) -> list[dict[str, Any]]:
    """The donor's own gifts in range, one row per program and calendar year. Employer matches
    are left out (D-127) and counted separately by `excluded_matches`."""
    _require_member(actor)
    rows = db.execute(
        text(
            """
            SELECT p.id AS program_id, p.name AS program,
                   EXTRACT(YEAR FROM g.gift_date)::int AS year,
                   count(*)::int AS gifts, sum(g.gross_cents)::bigint AS cents
            FROM gifts g JOIN programs p ON p.id = g.program_id
            WHERE g.donor_id = :d AND g.attribution = 'linked' AND g.deleted_at IS NULL
              AND NOT g.is_matching_gift AND g.gift_date BETWEEN :s AND :e
            GROUP BY p.id, p.name, year ORDER BY p.name, year
            """
        ),
        {"d": donor_id, "s": start, "e": end},
    )
    return [dict(r) for r in rows.mappings()]


def excluded_matches(
    db: Session, actor: Actor, *, donor_id: int, start: date, end: date
) -> dict[str, int]:
    _require_member(actor)
    row = (
        db.execute(
            text(
                """
                SELECT count(*)::int AS gifts, COALESCE(sum(gross_cents), 0)::bigint AS cents
                FROM gifts WHERE donor_id = :d AND attribution = 'linked' AND deleted_at IS NULL
                  AND is_matching_gift AND gift_date BETWEEN :s AND :e
                """
            ),
            {"d": donor_id, "s": start, "e": end},
        )
        .mappings()
        .one()
    )
    return {"gifts": row["gifts"], "cents": row["cents"]}
