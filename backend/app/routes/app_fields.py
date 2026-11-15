"""Settings > Fields: definitions for donors and gifts (CUS-1 to CUS-4)."""

from typing import Annotated

from fastapi import Query, Response

from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router
from app.schemas.common import ErrorOut
from app.schemas.fields import Entity, FieldCreate, FieldListOut, FieldOut, FieldPatch
from app.services.fields import service

router = session_router("fields")


@router.get("/fields")
def list_fields(cur: CurrentDep, db: DB, entity: Annotated[Entity, Query()]) -> FieldListOut:
    """Every field of one entity in display order, including deactivated ones."""
    return service.list_fields(db, cur.actor, entity)


@router.post("/fields", status_code=201, responses={409: {"model": ErrorOut}})
def create_field(body: FieldCreate, cur: CurrentDep, db: DB, clock: ClockDep) -> FieldOut:
    """Add a custom field. Needs `settings.manage`."""
    return service.create(db, clock, cur.actor, body)


@router.patch("/fields/{field_id}", responses={409: {"model": ErrorOut}})
def update_field(
    field_id: int, body: FieldPatch, cur: CurrentDep, db: DB, clock: ClockDep
) -> FieldOut:
    """Relabel, reorder, show in list, edit choices, require, deactivate or restore."""
    return service.update(db, clock, cur.actor, field_id, body)


@router.delete("/fields/{field_id}", status_code=204, responses={409: {"model": ErrorOut}})
def delete_field(field_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> Response:
    """Only a custom field that never held a value; otherwise 409 and deactivate it."""
    service.delete(db, clock, cur.actor, field_id)
    return Response(status_code=204)
