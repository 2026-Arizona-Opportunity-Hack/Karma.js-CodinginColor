"""Manage field definitions (CUS-1, CUS-2, D-145). Needs `settings.manage` (GOV-4).

Removing a field deactivates it: values stay and it can be restored. A custom field that never
held a value can be deleted for good. Built-ins are relabeled, reordered and hidden only."""

import re
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.clock import Clock
from app.db.models import FieldDefinition
from app.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.repos import audit
from app.schemas.fields import FieldCreate, FieldListOut, FieldMeta, FieldOut, FieldPatch

# The system reads these on every donor and gift, so they can never be hidden.
PROTECTED = {("donor", "first_name"), ("donor", "last_name"), ("donor", "email"),
             ("gift", "gift_date"), ("gift", "amount")}  # fmt: skip
_TABLE = {"donor": "donors", "gift": "gifts"}


def _require(actor: Actor) -> None:
    if not can(actor, Action.SETTINGS_MANAGE):
        raise Forbidden("You are not allowed to manage fields.")


def definitions(db: Session, entity: str, *, active_only: bool = False) -> list[FieldDefinition]:
    stmt = select(FieldDefinition).where(FieldDefinition.entity == entity)
    if active_only:
        stmt = stmt.where(FieldDefinition.is_active)
    return list(db.scalars(stmt.order_by(FieldDefinition.position, FieldDefinition.id)))


def meta(defs: list[FieldDefinition]) -> list[FieldMeta]:
    """Active fields in display order, for the `fields` list beside `custom` values."""
    return [FieldMeta.model_validate(d, from_attributes=True) for d in defs if d.is_active]


def has_values(db: Session, d: FieldDefinition) -> bool:
    if d.is_builtin:
        return True
    sql = f"SELECT EXISTS (SELECT 1 FROM {_TABLE[d.entity]} WHERE jsonb_exists(custom, :k))"  # noqa: S608
    return bool(db.execute(text(sql), {"k": d.key}).scalar_one())


def _out(db: Session, d: FieldDefinition) -> FieldOut:
    return FieldOut(
        **FieldMeta.model_validate(d, from_attributes=True).model_dump(),
        id=d.id, entity=d.entity, show_in_list=d.show_in_list, is_active=d.is_active,
        has_values=has_values(db, d),
    )  # fmt: skip


def list_fields(db: Session, actor: Actor, entity: str) -> FieldListOut:
    if actor.kind != "user":
        raise Forbidden("Sign in to see fields.")
    return FieldListOut(items=[_out(db, d) for d in definitions(db, entity)])


def _slug(db: Session, entity: str, label: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "field"
    if base[0].isdigit():
        base = f"f_{base}"
    taken = set(db.scalars(select(FieldDefinition.key).where(FieldDefinition.entity == entity)))
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    return key


def _check_choices(kind: str, choices: list[str] | None) -> list[str] | None:
    if kind in ("choice", "multi_choice"):
        clean = list(dict.fromkeys(choices or []))
        if not clean:
            raise Unprocessable("Choice fields need at least one choice.")
        return clean
    if choices:
        raise Unprocessable("Only choice fields have choices.")
    return None


def _next_position(db: Session, entity: str) -> int:
    top = db.scalar(
        select(func.max(FieldDefinition.position)).where(FieldDefinition.entity == entity)
    )
    return (top or 0) + 10


def create(db: Session, clock: Clock, actor: Actor, body: FieldCreate) -> FieldOut:
    _require(actor)
    taken = db.scalar(
        select(FieldDefinition.id).where(
            FieldDefinition.entity == body.entity,
            func.lower(FieldDefinition.label) == body.label.lower(),
            FieldDefinition.is_active,
        )
    )
    if taken:
        raise Conflict(f"A field called '{body.label}' already exists.")
    d = FieldDefinition(
        entity=body.entity, key=_slug(db, body.entity, body.label), label=body.label,
        type=body.type, choices=_check_choices(body.type, body.choices), is_builtin=False,
        is_required=body.is_required, is_contact=body.is_contact, show_in_list=body.show_in_list,
        position=_next_position(db, body.entity), created_by=actor.user_id,
        created_at=clock.now(), updated_at=clock.now(),
    )  # fmt: skip
    db.add(d)
    db.flush()
    audit.write(
        db, actor, "field.create", entity="field", entity_id=d.id,
        data={"entity": d.entity, "key": d.key, "type": d.type, "is_contact": d.is_contact},
        at=clock.now(),
    )  # fmt: skip
    return _out(db, d)


def _get(db: Session, field_id: int) -> FieldDefinition:
    d = db.get(FieldDefinition, field_id)
    if d is None:
        raise NotFound("No such field.")
    return d


def update(db: Session, clock: Clock, actor: Actor, field_id: int, body: FieldPatch) -> FieldOut:
    _require(actor)
    d = _get(db, field_id)
    changes: dict[str, Any] = body.model_dump(exclude_unset=True)
    if not changes:
        raise Unprocessable("Send at least one field to change.")
    for name in ("label", "position", "show_in_list", "is_required", "is_active"):
        if name in changes and changes[name] is None:
            raise Unprocessable(f"{name} cannot be cleared.")
    if d.is_builtin:
        locked = set(changes) & {"choices", "is_required"}
        if locked:
            raise Conflict(
                f"{d.label} is a built-in field. Only its label, order and visibility change."
            )
        if changes.get("is_active") is False and (d.entity, d.key) in PROTECTED:
            raise Conflict(f"{d.label} is needed by Compass and cannot be hidden.")
    if "choices" in changes:
        if d.type not in ("choice", "multi_choice"):
            raise Unprocessable("Only choice fields have choices.")
        changes["choices"] = _check_choices(d.type, changes["choices"])  # old values are kept
    if "label" in changes and changes["label"].lower() != d.label.lower():
        clash = db.scalar(select(FieldDefinition.id).where(
            FieldDefinition.entity == d.entity, FieldDefinition.id != d.id,
            FieldDefinition.is_active,
            func.lower(FieldDefinition.label) == changes["label"].lower(),
        ))  # fmt: skip
        if clash:
            raise Conflict(f"A field called '{changes['label']}' already exists.")
    before = {k: getattr(d, k) for k in changes}
    for name, value in changes.items():
        setattr(d, name, value)
    d.updated_at = clock.now()
    action = "field.update"
    if "is_active" in changes and before["is_active"] != d.is_active:
        action = "field.restore" if d.is_active else "field.deactivate"
    audit.write(
        db, actor, action, entity="field", entity_id=d.id,
        data={"key": d.key, "from": before, "to": changes}, at=clock.now(),
    )  # fmt: skip
    db.flush()
    return _out(db, d)


def delete(db: Session, clock: Clock, actor: Actor, field_id: int) -> None:
    _require(actor)
    d = _get(db, field_id)
    if d.is_builtin:
        raise Conflict(f"{d.label} is a built-in field. It can be hidden, not deleted.")
    if has_values(db, d):
        raise Conflict(f"{d.label} holds values. Deactivate it instead; the values are kept.")
    audit.write(
        db, actor, "field.delete", entity="field", entity_id=d.id,
        data={"entity": d.entity, "key": d.key}, at=clock.now(),
    )  # fmt: skip
    db.delete(d)
    db.flush()
