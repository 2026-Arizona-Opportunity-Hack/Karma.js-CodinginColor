"""Donor messages and the reminder digest. Lane C (Phase 3)."""

from typing import Annotated

from fastapi import Query

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

router = session_router("messages")
CONFLICT: dict[int | str, dict[str, object]] = {
    409: {"model": ErrorOut, "description": "Wrong state for this action (MSG-3)"}
}


@router.post("/donors/{donor_id}/messages", status_code=201)
def create_draft(donor_id: int, body: MessageCreate) -> MessageOut:
    todo("lane C, phase 3")


@router.post("/messages/draft-quarterly")
def draft_quarterly() -> DraftBatchOut:
    """Idempotent: never two open drafts of one kind for a donor (MSG-2)."""
    todo("lane C, phase 3")


@router.get("/messages")
def list_messages(status: Annotated[MessageStatus | None, Query()] = None) -> MessageListOut:
    todo("lane C, phase 3")


@router.patch("/messages/{message_id}", responses=CONFLICT)
def edit_message(message_id: int, body: MessageUpdate) -> MessageOut:
    todo("lane C, phase 3")


@router.post("/messages/{message_id}/approve", responses=CONFLICT)
def approve_message(message_id: int) -> MessageOut:
    todo("lane C, phase 3")


@router.post("/messages/{message_id}/send", responses=CONFLICT)
def send_message(message_id: int) -> MessageOut:
    """Only from `approved`, and only if the body hash still matches (MSG-3, MSG-4)."""
    todo("lane C, phase 3")


@router.post("/messages/{message_id}/mark-sent", responses=CONFLICT)
def mark_sent(message_id: int) -> MessageOut:
    """For text messages sent from the person's own phone (MSG-5)."""
    todo("lane C, phase 3")


@router.post("/messages/{message_id}/cancel", responses=CONFLICT)
def cancel_message(message_id: int) -> MessageOut:
    todo("lane C, phase 3")


@router.post("/digest/send")
def send_digest() -> DigestRunOut:
    """Sent only by a person's click, dry-run by default (REM-6, D-109)."""
    todo("lane C, phase 3")
