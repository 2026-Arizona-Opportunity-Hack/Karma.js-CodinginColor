"""Donor reads. History and timeline are visible to every member (D-104); contact fields are
decided per donor by `policy.can(actor, "donor.view_contact", donor)` in the service.
Totals count linked gifts only (DED-5, DED-8)."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.errors import Forbidden, NotFound

NEW_WINDOW_DAYS = 30  # "new": first gift in the last 30 days


@dataclass
class OwnedBy:
    """Just enough of a donor for `policy.can`."""

    owner_user_id: int | None


def _require_member(actor: Actor) -> None:
    if not can(actor, Action.DONOR_VIEW, OwnedBy(None)):
        raise Forbidden("Sign in to see donors.")


# One row per donor with the numbers a donor card needs. `cur` and `prev` follow DATA_MODEL 3.5.
_CARD_SQL = """
SELECT d.id, d.kind, d.display_name, d.first_name, d.last_name, d.organization, d.email, d.phone,
       d.notes, d.owner_user_id, d.do_not_contact, d.created_at, d.custom,
       u.display_name AS owner_name, COALESCE(u.is_active, true) AS owner_active,
       COALESCE(g.t12, 0)::bigint AS total_12m_cents,
       COALESCE(g.tall, 0)::bigint AS total_lifetime_cents,
       g.last_gift_date, i.last_contact_date, ns.title AS next_step_title,
       ns.due_date AS next_step_due,
       (g.first_gift_date IS NOT NULL AND g.first_gift_date > :new_since) AS is_new,
       (COALESCE(g.t12, 0) = 0 AND COALESCE(g.prev, 0) > 0) AS is_lapsed
FROM donors d
LEFT JOIN users u ON u.id = d.owner_user_id
LEFT JOIN LATERAL (
    SELECT sum(gross_cents) AS tall,
           sum(gross_cents) FILTER (WHERE gift_date > :t365) AS t12,
           sum(gross_cents) FILTER (WHERE gift_date > :t730 AND gift_date <= :t365) AS prev,
           max(gift_date) AS last_gift_date, min(gift_date) AS first_gift_date
    FROM gifts WHERE donor_id = d.id AND attribution = 'linked' AND deleted_at IS NULL
      AND NOT is_matching_gift AND gift_date <= :today
) g ON true
LEFT JOIN LATERAL (
    SELECT max(occurred_on) AS last_contact_date
    FROM interactions WHERE donor_id = d.id AND kind <> 'system'
) i ON true
LEFT JOIN next_steps ns ON ns.donor_id = d.id AND ns.status = 'open'
WHERE d.deleted_at IS NULL AND d.merged_into_id IS NULL
"""

STATUS_FILTERS = {
    "new": "is_new",
    "lapsed": "is_lapsed",
    "owner_inactive": "NOT owner_active",
    "do_not_contact": "do_not_contact",
}


def _day_params(today: date) -> dict[str, Any]:
    return {
        "today": today,
        "t365": today - timedelta(days=365),
        "t730": today - timedelta(days=730),
        "new_since": today - timedelta(days=NEW_WINDOW_DAYS),
    }


def list_cards(
    db: Session,
    actor: Actor,
    *,
    today: date,
    scope: str,
    q: str | None,
    owner: int | None,
    status: str | None,
    program: int | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    _require_member(actor)
    where = ["TRUE"]
    params: dict[str, Any] = {
        **_day_params(today),
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if scope == "mine":
        where.append("owner_user_id = :me")
        params["me"] = actor.user_id
    if owner is not None:
        where.append("owner_user_id = :owner")
        params["owner"] = owner
    if status is not None:
        where.append(STATUS_FILTERS[status])
    if program is not None:
        where.append(
            "EXISTS (SELECT 1 FROM gifts pg WHERE pg.donor_id = x.id AND pg.program_id = :program "
            "AND pg.deleted_at IS NULL AND pg.attribution = 'linked')"
        )
        params["program"] = program
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["like"] = f"%{escaped}%"
        clauses = ["display_name ILIKE :like", "organization ILIKE :like"]
        # Searching by email would reveal it, so only where the actor may see contact details.
        if can(actor, Action.DONOR_VIEW_CONTACT, OwnedBy(-1)):  # an active super admin
            clauses.append("email ILIKE :like")
        elif can(actor, Action.DONOR_VIEW_CONTACT, OwnedBy(actor.id)):  # their own donors
            clauses.append("(email ILIKE :like AND owner_user_id = :me2)")
            params["me2"] = actor.user_id
        where.append("(" + " OR ".join(clauses) + ")")
    cond = " AND ".join(where)
    sql = (
        f"SELECT x.*, count(*) OVER () AS total_rows FROM ({_CARD_SQL}) x "  # noqa: S608
        f"WHERE {cond} ORDER BY lower(x.display_name), x.id LIMIT :limit OFFSET :offset"
    )
    rows = [dict(r) for r in db.execute(text(sql), params).mappings()]
    if rows:
        return rows, int(rows[0]["total_rows"])
    # A page past the end has no row to carry the window count.
    count_sql = f"SELECT count(*) FROM ({_CARD_SQL}) x WHERE {cond}"  # noqa: S608
    return rows, int(db.execute(text(count_sql), params).scalar_one())


def get_card(db: Session, actor: Actor, donor_id: int, *, today: date) -> dict[str, Any]:
    _require_member(actor)
    sql = f"SELECT * FROM ({_CARD_SQL}) x WHERE x.id = :id"  # noqa: S608
    row = db.execute(text(sql), {**_day_params(today), "id": donor_id}).mappings().first()
    if row is None:
        raise NotFound("Donor not found.")
    return dict(row)


_GIFT_COLUMNS = """
g.id, g.donor_id, d.display_name AS donor_name, g.attribution, g.source, g.gift_date,
g.gross_cents, g.fee_cents, g.net_cents, p.name AS program, g.campaign_name,
g.is_matching_gift, g.payer_name, g.assumed_thanked, g.custom,
d.owner_user_id AS donor_owner_id
"""


def recent_gifts(
    db: Session, actor: Actor, donor_ids: list[int], *, limit: int = 5
) -> dict[int, list[dict[str, Any]]]:
    """The last `limit` linked gifts per donor, newest first."""
    _require_member(actor)
    out: dict[int, list[dict[str, Any]]] = {i: [] for i in donor_ids}
    if not donor_ids:
        return out
    sql = f"""
        SELECT * FROM (
          SELECT {_GIFT_COLUMNS},
                 row_number() OVER (
                   PARTITION BY g.donor_id ORDER BY g.gift_date DESC, g.id DESC) AS rn
          FROM gifts g JOIN programs p ON p.id = g.program_id
          JOIN donors d ON d.id = g.donor_id
          WHERE g.donor_id = ANY(:ids) AND g.deleted_at IS NULL AND g.attribution = 'linked'
        ) t WHERE rn <= :limit ORDER BY donor_id, gift_date DESC, id DESC
    """  # noqa: S608
    for r in db.execute(text(sql), {"ids": donor_ids, "limit": limit}).mappings():
        out[r["donor_id"]].append(dict(r))
    return out


def unattributed_gifts(db: Session, actor: Actor, *, limit: int = 500) -> list[dict[str, Any]]:
    """Anonymous and pending-review gifts (DED-8), newest first."""
    _require_member(actor)
    sql = f"""
        SELECT {_GIFT_COLUMNS} FROM gifts g JOIN programs p ON p.id = g.program_id
        LEFT JOIN donors d ON d.id = g.donor_id
        WHERE g.deleted_at IS NULL AND g.attribution IN ('anonymous','pending_review')
        ORDER BY g.gift_date DESC, g.id DESC LIMIT :limit
    """  # noqa: S608
    return [dict(r) for r in db.execute(text(sql), {"limit": limit}).mappings()]


def timeline(db: Session, actor: Actor, donor_id: int, *, limit: int = 500) -> list[dict[str, Any]]:
    """Gifts, sent messages, contacts, notes, next steps and owner changes, newest first."""
    _require_member(actor)
    sql = """
    SELECT * FROM (
      SELECT 'gift' AS kind, (g.gift_date::timestamp AT TIME ZONE 'America/Phoenix') AS at,
             'Gift to ' || p.name AS title, NULLIF(g.campaign_name, '') AS detail,
             NULL::text AS by, g.gross_cents AS amount_cents, g.id AS entity_id
        FROM gifts g JOIN programs p ON p.id = g.program_id
        WHERE g.donor_id = :id AND g.attribution = 'linked' AND g.deleted_at IS NULL
      UNION ALL
      SELECT CASE WHEN i.kind = 'note' THEN 'note' ELSE 'contact' END,
             CASE WHEN (i.created_at AT TIME ZONE 'America/Phoenix')::date = i.occurred_on
                  THEN i.created_at  -- logged the same day: keep real order with same-day events
                  ELSE (i.occurred_on::timestamp AT TIME ZONE 'America/Phoenix') END,
             initcap(replace(i.kind, '_', ' ')), i.summary, u.display_name, NULL, i.id
        FROM interactions i LEFT JOIN users u ON u.id = i.user_id
        WHERE i.donor_id = :id AND i.kind <> 'system' AND i.message_id IS NULL
      UNION ALL
      SELECT 'message', m.sent_at, initcap(replace(m.kind, '_', ' ')) || ' sent', m.subject,
             u.display_name, NULL, m.id
        FROM messages m LEFT JOIN users u ON u.id = m.sent_by
        WHERE m.donor_id = :id AND m.status IN ('sent','sent_manually')
      UNION ALL
      SELECT 'next_step', n.created_at, 'Next step: ' || n.title,
             'Due ' || to_char(n.due_date, 'YYYY-MM-DD'), u.display_name, NULL, n.id
        FROM next_steps n LEFT JOIN users u ON u.id = n.created_by WHERE n.donor_id = :id
      UNION ALL
      SELECT 'owner_change', h.changed_at,
             CASE WHEN f.id IS NULL THEN 'Assigned to ' || t.display_name
                  ELSE 'Moved from ' || f.display_name || ' to ' || t.display_name END,
             h.reason, b.display_name, NULL, h.id
        FROM owner_history h JOIN users t ON t.id = h.to_user_id
        LEFT JOIN users f ON f.id = h.from_user_id LEFT JOIN users b ON b.id = h.changed_by
        WHERE h.donor_id = :id
    ) t WHERE at IS NOT NULL ORDER BY at DESC, kind, entity_id DESC LIMIT :limit
    """
    return [dict(r) for r in db.execute(text(sql), {"id": donor_id, "limit": limit}).mappings()]


def gift_row(db: Session, actor: Actor, gift_id: int) -> dict[str, Any]:
    """One gift in the shape of `GiftOut`."""
    _require_member(actor)
    sql = f"""
        SELECT {_GIFT_COLUMNS} FROM gifts g JOIN programs p ON p.id = g.program_id
        LEFT JOIN donors d ON d.id = g.donor_id WHERE g.id = :id AND g.deleted_at IS NULL
    """  # noqa: S608
    row = db.execute(text(sql), {"id": gift_id}).mappings().first()
    if row is None:
        raise NotFound("Gift not found.")
    return dict(row)
