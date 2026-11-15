"""Assistant: interpret one sentence into proposed actions. No writes (AST-1 to AST-3).

The browser then calls the existing endpoints itself, after the member confirms."""

from typing import Annotated

from fastapi import Depends

from app.errors import Forbidden
from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router
from app.schemas.assistant import InterpretIn, InterpretOut
from app.schemas.common import ErrorOut
from app.services.ai.gateway import Gateway, get_gateway
from app.services.assistant import service

router = session_router("assistant")


@router.post(
    "/assistant/interpret",
    responses={
        404: {"model": ErrorOut, "description": "The assistant setting is off"},
        429: {"model": ErrorOut, "description": "More than 20 requests a minute"},
        503: {"model": ErrorOut, "description": "The AI gateway is down"},
    },
)
def interpret(
    body: InterpretIn,
    cur: CurrentDep,
    db: DB,
    clock: ClockDep,
    gateway: Annotated[Gateway, Depends(get_gateway)],
) -> InterpretOut:
    """Proposes actions from one sentence (max 500 characters). The donor list never goes to
    the model; names are matched here, among donors you may act on. Full-access keys get 403."""
    if cur.actor.full_access:
        raise Forbidden("The assistant is for signed-in members only.")
    return service.interpret(db, clock, cur.actor, gateway, body.text)
