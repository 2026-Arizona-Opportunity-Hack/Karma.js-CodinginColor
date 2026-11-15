"""Facts the lapsed-donor radar adds to a retention row (RPT-2, MSG-8). Read-only."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.errors import Forbidden


def facts(db: Session, actor: Actor, donor_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Per donor: owner, do-not-contact flag, whether we can write to them, last own gift date and
    the id of an open lapsed-nudge draft, if any."""
    if actor.kind not in ("user", "cli"):
        raise Forbidden("Not allowed to read the lapsed list.")
    if not donor_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT d.id, d.owner_user_id, u.display_name AS owner_name, d.do_not_contact,
                   d.email IS NOT NULL AS has_email,
                   (d.email IS NOT NULL OR d.phone IS NOT NULL) AS reachable,
                   (SELECT max(g.gift_date) FROM gifts g
                     WHERE g.donor_id = d.id AND g.attribution = 'linked'
                       AND g.deleted_at IS NULL AND NOT g.is_matching_gift) AS last_gift,
                   (SELECT m.id FROM messages m
                     WHERE m.donor_id = d.id AND m.kind = 'lapsed_nudge'
                       AND m.status IN ('draft','approved') LIMIT 1) AS draft_id
            FROM donors d LEFT JOIN users u ON u.id = d.owner_user_id
            WHERE d.id = ANY(:ids)
            """
        ),
        {"ids": donor_ids},
    )
    return {r["id"]: dict(r) for r in rows.mappings()}
