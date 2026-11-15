"""Shared building blocks for the app API contract (docs/API.md section 3).

Money is integer cents everywhere; the UI formats it. Dates are business dates in
America/Phoenix; timestamps are UTC ISO strings.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
Phone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=40, pattern=r"^[0-9+()\-.\s]{7,40}$"),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Cents = Annotated[int, Field(ge=0, le=10_000_000_00, description="Integer cents, USD")]

DonorKind = Literal["person", "organization", "funder"]
DonorStatus = Literal[
    "new", "thank_you_due", "update_due", "lapsed", "owner_inactive", "do_not_contact"
]
ImportSource = Literal["spreadsheet", "zeffy", "benevity", "generic"]
ImportStatus = Literal["previewed", "committed", "reversed", "expired"]
MessageKind = Literal["thank_you", "quarterly_update", "lapsed_nudge", "event_invite"]
Channel = Literal["email", "sms"]
MessageStatus = Literal["draft", "approved", "sent", "sent_manually", "cancelled", "failed"]
DeliveryMode = Literal["dry_run", "live", "manual"]
ContactKind = Literal["call", "text", "email", "meeting", "note"]
ReassignScope = Literal["anyone", "own_only"]


class ErrorDetail(BaseModel):
    code: str = Field(examples=["forbidden"])
    message: str


class ErrorOut(BaseModel):
    """Body of every 4xx/5xx: `{"error": {"code": ..., "message": ...}}`."""

    error: ErrorDetail


class MemberRef(BaseModel):
    id: int
    display_name: str
    is_active: bool = True


class CountCents(BaseModel):
    count: int
    cents: int
