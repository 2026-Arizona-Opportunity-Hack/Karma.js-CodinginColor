"""Donor messages and the reminder digest (MSG-1 to MSG-8, REM-6).

State machine: draft -> approved -> sent (or sent_manually for SMS), plus cancelled and
failed. Only a person approves; the server rejects send from any state but approved.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import (
    Channel,
    DeliveryMode,
    MemberRef,
    MessageKind,
    MessageStatus,
)


class MessageCreate(BaseModel):
    """Create a draft from the template for `kind` and `channel` (MSG-2, idempotent)."""

    kind: MessageKind
    channel: Channel
    gift_id: int | None = Field(default=None, description="Required for thank_you")


class MessageUpdate(BaseModel):
    """Editing an approved message returns it to draft (MSG-3)."""

    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)


class MessageOut(BaseModel):
    id: int
    donor_id: int
    donor_name: str
    gift_id: int | None = None
    kind: MessageKind
    channel: Channel
    status: MessageStatus
    subject: str | None = None
    body: str
    created_by: MemberRef | None = None
    approved_by: MemberRef | None = None
    sent_by: MemberRef | None = None
    created_at: datetime
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    delivery_mode: DeliveryMode | None = None
    provider_ref: str | None = None
    error: str | None = None
    sms_link: str | None = Field(
        default=None, description="Pre-filled `sms:` link for approved text messages (MSG-5)"
    )


class MessageListOut(BaseModel):
    items: list[MessageOut]


class DraftBatchOut(BaseModel):
    created: int
    skipped_existing: int = Field(description="Donors that already had an open draft")
    messages: list[MessageOut]


class DigestMember(BaseModel):
    member: MemberRef
    thank_you_due: int
    quarterly_due: int
    next_step_due: int
    needs_reassignment: int


class DigestRunOut(BaseModel):
    id: int
    run_at: datetime
    mode: DeliveryMode
    recipients: int
    members: list[DigestMember]
