"""Donors, gifts, ownership, timeline, contacts, next steps and reminders (DON, OWN, REM)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import (
    Cents,
    ContactKind,
    DonorKind,
    DonorStatus,
    Email,
    ErrorDetail,
    LongText,
    MemberRef,
    Phone,
    ShortText,
)


class GiftOut(BaseModel):
    id: int
    donor_id: int | None
    donor_name: str | None = Field(description="Null for anonymous or pending-review gifts")
    attribution: Literal["linked", "anonymous", "pending_review"]
    source: Literal["zeffy", "benevity", "generic", "manual"]
    gift_date: date
    gross_cents: int
    fee_cents: int
    net_cents: int
    program: str
    campaign_name: str | None = None
    is_matching_gift: bool = False
    payer_name: str | None = None
    assumed_thanked: bool = False


class GiftCreate(BaseModel):
    """A manual gift, for example a check (DON-8)."""

    gift_date: date
    gross_cents: Cents = Field(gt=0)
    program_id: int | None = Field(default=None, description="Defaults to General")
    note: LongText | None = None


class GiftListOut(BaseModel):
    items: list[GiftOut]


class DonorCard(BaseModel):
    """A list item (DON-5)."""

    id: int
    kind: DonorKind
    display_name: str
    organization: str | None = None
    owner: MemberRef | None
    total_12m_cents: int
    total_lifetime_cents: int
    last_gift_date: date | None = None
    last_contact_date: date | None = None
    next_step_title: str | None = None
    next_step_due: date | None = None
    statuses: list[DonorStatus]
    recent_gifts: list[GiftOut] = Field(description="Last 5, newest first")


class DonorDetail(DonorCard):
    first_name: str | None = None
    last_name: str | None = None
    # Contact details appear only for the owner and an active super admin (DON-3, D-104).
    email: str | None = None
    phone: str | None = None
    contact_visible: bool
    contact_via: str | None = Field(default=None, description="Owner's name when hidden")
    do_not_contact: bool
    notes: str | None = None
    can_act: bool
    can_reassign: bool
    created_at: datetime


class DonorPage(BaseModel):
    items: list[DonorCard]
    total: int
    page: int
    page_size: int


class DonorCreate(BaseModel):
    kind: DonorKind
    display_name: ShortText
    first_name: ShortText | None = None
    last_name: ShortText | None = None
    organization: ShortText | None = None
    email: Email | None = None
    phone: Phone | None = None
    do_not_contact: bool = False
    notes: LongText | None = None
    confirm_new: bool = Field(
        default=False, description="Create anyway after a 409 possible-duplicate warning (DED-6)"
    )


class DonorUpdate(BaseModel):
    display_name: ShortText | None = None
    first_name: ShortText | None = None
    last_name: ShortText | None = None
    organization: ShortText | None = None
    email: Email | None = None
    phone: Phone | None = None
    do_not_contact: bool | None = None
    notes: LongText | None = None


class DuplicateCandidate(BaseModel):
    donor_id: int
    display_name: str
    owner: MemberRef | None = None
    match_reason: Literal["email", "phone", "name_employer"]


class PossibleDuplicateOut(BaseModel):
    """409 body for `POST /donors` (DED-6)."""

    error: ErrorDetail
    candidates: list[DuplicateCandidate]


class MergeIn(BaseModel):
    """Merge this donor into `into_id`; the older record's owner is kept (DED-7)."""

    into_id: int


class ReassignIn(BaseModel):
    to_user_id: int
    reason: LongText | None = None


class OwnerHistoryEntry(BaseModel):
    id: int
    from_user: MemberRef | None
    to_user: MemberRef
    changed_by: MemberRef | None = Field(description="Null when done by the system")
    method: Literal["round_robin", "manual", "bulk", "merge"]
    reason: str | None = None
    changed_at: datetime


class OwnerHistoryOut(BaseModel):
    items: list[OwnerHistoryEntry]


class TimelineEntry(BaseModel):
    """One line of the donor timeline, newest first (DON-6)."""

    kind: Literal["gift", "message", "contact", "note", "next_step", "owner_change"]
    at: datetime
    title: str
    detail: str | None = None
    by: str | None = None
    amount_cents: int | None = None
    entity_id: int | None = None


class TimelineOut(BaseModel):
    items: list[TimelineEntry]


class InteractionCreate(BaseModel):
    """Log a contact in three taps (DON-9)."""

    kind: ContactKind
    summary: LongText | None = None
    occurred_on: date | None = Field(default=None, description="Defaults to today")


class InteractionOut(BaseModel):
    id: int
    donor_id: int
    kind: str
    occurred_on: date
    summary: str | None = None
    user: MemberRef | None = None


class NextStepIn(BaseModel):
    title: ShortText
    due_date: date


class NextStepOut(BaseModel):
    id: int
    donor_id: int
    title: str
    due_date: date
    status: Literal["open", "done", "cancelled"]
    done_at: datetime | None = None


class ReminderOut(BaseModel):
    """Derived from data, never stored (REM-1 to REM-5)."""

    type: Literal["thank_you_due", "quarterly_due", "next_step_due", "needs_reassignment"]
    donor_id: int
    donor_name: str
    owner: MemberRef | None
    due_date: date | None = None
    overdue: bool = False
    gift_id: int | None = None
    next_step_id: int | None = None
    action: Literal["draft_thank_you", "draft_update", "log_contact", "open_next_step", "reassign"]


class ReminderListOut(BaseModel):
    items: list[ReminderOut]
