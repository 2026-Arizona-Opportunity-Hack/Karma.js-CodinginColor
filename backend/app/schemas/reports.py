"""Dashboard summary and retention (RPT-1, RPT-2). The funder export returns HTML or CSV."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import MemberRef


class PeriodTotals(BaseModel):
    gross_cents: int
    gift_count: int
    donor_count: int


class ProgramTotal(BaseModel):
    program: str
    gross_cents: int
    gift_count: int
    donor_count: int


class BoardMemberTotal(BaseModel):
    member: MemberRef
    donors_owned: int
    gross_cents: int
    open_reminders: int


class ReportSummary(BaseModel):
    as_of: datetime
    this_month: PeriodTotals
    this_quarter: PeriodTotals
    last_12_months: PeriodTotals
    by_program: list[ProgramTotal]
    by_board_member: list[BoardMemberTotal]
    open_reminders: int
    unattributed_gifts: int


RetentionClassName = Literal["new", "reactivated", "increased", "same", "decreased", "lapsed"]


class RetentionClass(BaseModel):
    donors: int
    cents_cur: int
    cents_prev: int


class RetentionDonor(BaseModel):
    donor_id: int
    display_name: str
    cents_cur: int
    cents_prev: int


class RetentionReport(BaseModel):
    as_of: date
    basis: Literal["rolling", "calendar"]
    classes: dict[RetentionClassName, RetentionClass]
    donors: dict[RetentionClassName, list[RetentionDonor]]
