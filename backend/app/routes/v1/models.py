"""Response models for `/api/v1`. Aggregates only: no donor name, email, phone, note or id
(API-2). A test walks the OpenAPI schema and fails on any such field."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Period = Literal["month", "quarter", "year"]


class V1Response(BaseModel):
    """Every response says when it was computed and that money is USD cents."""

    as_of: datetime
    currency: Literal["USD"] = "USD"


class RangedResponse(V1Response):
    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from")
    to: date


class PeriodItem(BaseModel):
    period_start: date
    gross_cents: int
    net_cents: int
    gift_count: int
    donor_count: int


class ByPeriod(RangedResponse):
    period: Period
    items: list[PeriodItem]


class ProgramItem(BaseModel):
    program: str
    gross_cents: int
    gift_count: int
    donor_count: int


class ByProgram(RangedResponse):
    items: list[ProgramItem]


class BoardMemberItem(BaseModel):
    board_member: str
    donors_owned: int
    gross_cents: int
    open_reminders: int = Field(description="0 until the reminders service lands (Phase 3)")
    contacts_logged: int
    messages_sent: int


class ByBoardMember(RangedResponse):
    items: list[BoardMemberItem]


class ActivityDay(BaseModel):
    day: date
    gifts_received: int
    gross_cents: int
    contacts_logged: int
    messages_sent: int


class RecentActivity(V1Response):
    days: int
    items: list[ActivityDay]
