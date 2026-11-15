"""Dashboard summary for the app's Reports page (RPT-1)."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock, today
from app.repos import reports as repo
from app.schemas.common import MemberRef
from app.schemas.reports import (
    BoardMemberTotal,
    PeriodTotals,
    ProgramTotal,
    ReportSummary,
    TopDonor,
    TopGift,
)


def _period(db: Session, actor: Actor, start: date, end: date) -> PeriodTotals:
    t = repo.totals(db, actor, start=start, end=end)
    return PeriodTotals(
        gross_cents=t["gross_cents"], gift_count=t["gift_count"], donor_count=t["donor_count"]
    )


def build(db: Session, clock: Clock, actor: Actor) -> ReportSummary:
    end = today(clock)
    month_start = end.replace(day=1)
    quarter_start = date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
    year_start = end - timedelta(days=364)
    return ReportSummary(
        as_of=clock.now(),
        this_month=_period(db, actor, month_start, end),
        this_quarter=_period(db, actor, quarter_start, end),
        last_12_months=_period(db, actor, year_start, end),
        by_program=[
            ProgramTotal(**r) for r in repo.by_program(db, actor, start=year_start, end=end)
        ],
        by_board_member=[
            BoardMemberTotal(
                member=MemberRef(
                    id=r["member_id"], display_name=r["board_member"], is_active=r["is_active"]
                ),
                donors_owned=r["donors_owned"],
                gross_cents=r["gross_cents"],
                open_reminders=0,  # derived reminders arrive with lane A in Phase 3
            )
            for r in repo.by_board_member(db, actor, start=year_start, end=end)
        ],
        top_donors=[TopDonor(**r) for r in repo.top_donors(db, actor, start=year_start, end=end)],
        top_gifts=[TopGift(**r) for r in repo.top_gifts(db, actor, start=year_start, end=end)],
        open_reminders=0,
        unattributed_gifts=repo.unattributed_count(db, actor),
    )
