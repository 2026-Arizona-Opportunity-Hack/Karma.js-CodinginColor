"""Donor lookup for the assistant: only donors the actor may act on (DON-4). Read-only."""

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import AppSetting
from app.errors import Forbidden
from app.repos.donors import OwnedBy
from app.services.assistant.tools import Target


def is_enabled(db: Session) -> bool:
    row = db.get(AppSetting, "assistant_enabled")
    return row is not None and row.value in (True, "true")


def _like(word: str) -> str:
    return "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def find_targets(
    db: Session, actor: Actor, name: str, *, today: date, limit: int = 6
) -> list[Target]:
    """Donors whose name or organization contains every word of `name`, limited to the donors
    this actor can act on: their own, or all of them for an active super admin."""
    if not can(actor, Action.DONOR_VIEW, OwnedBy(None)):
        raise Forbidden("Sign in to see donors.")
    words = name.split()[:6]
    if not words:
        return []
    params: dict[str, Any] = {"today": today, "limit": limit}
    where = ["d.deleted_at IS NULL", "d.merged_into_id IS NULL"]
    for i, word in enumerate(words):
        params[f"w{i}"] = _like(word)
        where.append(f"(d.display_name ILIKE :w{i} OR d.organization ILIKE :w{i})")
    if not can(actor, Action.DONOR_ACT, OwnedBy(-1)):  # not an active super admin
        where.append("d.owner_user_id = :me")
        params["me"] = actor.user_id
    conditions = " AND ".join(where)
    sql = f"""
        SELECT d.id, d.display_name, d.owner_user_id,
               (SELECT g.id FROM gifts g
                 WHERE g.donor_id = d.id AND g.attribution = 'linked' AND g.deleted_at IS NULL
                   AND NOT g.is_matching_gift AND g.gift_date <= :today
                 ORDER BY g.gift_date DESC, g.id DESC LIMIT 1) AS gift_id
        FROM donors d WHERE {conditions}
        ORDER BY lower(d.display_name), d.id LIMIT :limit
    """  # noqa: S608
    rows = db.execute(text(sql), params).mappings()
    return [Target(r["id"], r["display_name"], r["owner_user_id"], r["gift_id"]) for r in rows]
