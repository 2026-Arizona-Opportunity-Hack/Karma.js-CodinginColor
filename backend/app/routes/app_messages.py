"""Donor messages and the reminder digest. Lane C (Phase 3)."""

from typing import Annotated

from fastapi import Query, Response

from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router, todo
from app.schemas.common import ErrorOut, MessageStatus
from app.schemas.messages import (
    DigestRunOut,
    DraftBatchOut,
    MessageCreate,
    MessageListOut,
    MessageOut,
    MessageUpdate,
)
from app.services.messaging import service as messaging
from app.services.messaging import workflow

router = session_router("messages")
CONFLICT: dict[int | str, dict[str, object]] = {
    409: {"model": ErrorOut, "description": "Wrong state for this action (MSG-3)"}
}


@router.post("/donors/{donor_id}/messages", status_code=201)
def create_draft(
    donor_id: int, body: MessageCreate, cur: CurrentDep, db: DB, response: Response
) -> MessageOut:
    """Idempotent: asking again returns the open draft with 200 instead of 201 (MSG-2)."""
    out, created = messaging.create_draft(db, cur.actor, donor_id, body)
    response.status_code = 201 if created else 200
    return out


@router.post("/messages/draft-quarterly")
def draft_quarterly() -> DraftBatchOut:
    """Idempotent: never two open drafts of one kind for a donor (MSG-2)."""
    todo("lane C, phase 3")


@router.get("/messages")
def list_messages(
    cur: CurrentDep, db: DB, status: Annotated[MessageStatus | None, Query()] = None
) -> MessageListOut:
    return messaging.list_messages(db, cur.actor, status)


@router.patch("/messages/{message_id}", responses=CONFLICT)
def edit_message(message_id: int, body: MessageUpdate, cur: CurrentDep, db: DB) -> MessageOut:
    """An edit returns an approved message to draft and clears the approval (MSG-3)."""
    return workflow.edit(db, cur.actor, message_id, body)


@router.post("/messages/{message_id}/approve", responses=CONFLICT)
def approve_message(message_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> MessageOut:
    """Only a draft; records who and when and fixes the hash of the words (MSG-4)."""
    return workflow.approve(db, cur.actor, message_id, at=clock.now())


@router.post("/messages/{message_id}/send", responses=CONFLICT)
def send_message(message_id: int) -> MessageOut:
    """Only from `approved`, and only if the body hash still matches (MSG-3, MSG-4)."""
    todo("lane C, phase 3")


@router.post("/messages/{message_id}/mark-sent", responses=CONFLICT)
def mark_sent(message_id: int) -> MessageOut:
    """For text messages sent from the person's own phone (MSG-5)."""
    todo("lane C, phase 3")


@router.post("/messages/{message_id}/cancel", responses=CONFLICT)
def cancel_message(message_id: int, cur: CurrentDep, db: DB) -> MessageOut:
    return workflow.cancel(db, cur.actor, message_id)


@router.post("/digest/send")
def send_digest() -> DigestRunOut:
    """Sent only by a person's click, dry-run by default (REM-6, D-109)."""
    todo("lane C, phase 3")
