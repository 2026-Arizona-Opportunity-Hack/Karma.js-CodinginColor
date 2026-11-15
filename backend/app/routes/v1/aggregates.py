"""Read-only aggregate endpoints (docs/API.md 1.2). Auth, scope and rate limit come from the
`api_key` dependency; every query goes through a repository function that takes the Actor."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.clock import today
from app.repos import reports
from app.routes.deps import DB, ClockDep
from app.routes.v1.auth import ApiActorDep, api_key
from app.routes.v1.models import (
    ActivityDay,
    BoardMemberItem,
    ByBoardMember,
    ByPeriod,
    ByProgram,
    Period,
    PeriodItem,
    ProgramItem,
    RecentActivity,
    Retention,
    RetentionClassTotals,
    Summary,
)
from app.schemas.common import ErrorOut
from app.services.reports import retention as retention_service
from app.services.reports.aggregates import resolve_range

router = APIRouter(
    prefix="/api/v1",
    tags=["v1"],
    dependencies=[Depends(api_key)],
    responses={
        401: {"model": ErrorOut, "description": "Missing, invalid or revoked API key"},
        403: {"model": ErrorOut, "description": "Key lacks the read:aggregates scope"},
        429: {"model": ErrorOut, "description": "Over 60 requests per minute; see Retry-After"},
    },
)

From = Annotated[date | None, Query(alias="from", description="First day, default 12 months ago")]
To = Annotated[date | None, Query(description="Last day, default today")]


@router.get("/summary")
def summary(
    db: DB, clock: ClockDep, actor: ApiActorDep, from_: From = None, to: To = None
) -> Summary:
    start, end = resolve_range(clock, from_, to)
    return Summary(as_of=clock.now(), **{"from": start}, to=end, **reports.totals(
        db, actor, start=start, end=end
    ))  # fmt: skip


@router.get("/retention")
def retention(
    db: DB,
    clock: ClockDep,
    actor: ApiActorDep,
    as_of: Annotated[date | None, Query(description="Default today")] = None,
    basis: Annotated[Literal["rolling", "calendar"], Query()] = "rolling",
) -> Retention:
    result = retention_service.build(db, actor, as_of=as_of or today(clock), basis=basis)
    return Retention(
        as_of=clock.now(),
        retention_date=result.as_of,
        basis=result.basis,
        classes={k: RetentionClassTotals(**v.model_dump()) for k, v in result.classes.items()},
    )


@router.get("/totals/by-period")
def totals_by_period(
    db: DB,
    clock: ClockDep,
    actor: ApiActorDep,
    period: Annotated[Period, Query()] = "month",
    from_: From = None,
    to: To = None,
) -> ByPeriod:
    start, end = resolve_range(clock, from_, to)
    rows = reports.by_period(db, actor, start=start, end=end, period=period)
    return ByPeriod(
        as_of=clock.now(), **{"from": start}, to=end, period=period,
        items=[PeriodItem(**r) for r in rows],
    )  # fmt: skip


@router.get("/totals/by-program")
def totals_by_program(
    db: DB, clock: ClockDep, actor: ApiActorDep, from_: From = None, to: To = None
) -> ByProgram:
    start, end = resolve_range(clock, from_, to)
    rows = reports.by_program(db, actor, start=start, end=end)
    return ByProgram(
        as_of=clock.now(), **{"from": start}, to=end, items=[ProgramItem(**r) for r in rows]
    )


@router.get("/totals/by-board-member")
def totals_by_board_member(
    db: DB, clock: ClockDep, actor: ApiActorDep, from_: From = None, to: To = None
) -> ByBoardMember:
    start, end = resolve_range(clock, from_, to)
    rows = reports.by_board_member(db, actor, start=start, end=end)
    return ByBoardMember(
        as_of=clock.now(),
        **{"from": start},
        to=end,
        items=[BoardMemberItem.model_validate({**r, "open_reminders": 0}) for r in rows],
    )


@router.get("/activity/recent")
def recent_activity(
    db: DB,
    clock: ClockDep,
    actor: ApiActorDep,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> RecentActivity:
    end = today(clock)
    rows = reports.activity_by_day(db, actor, start=end - timedelta(days=days - 1), end=end)
    return RecentActivity(
        as_of=clock.now(),
        days=days,
        items=[ActivityDay(**r) for r in rows],
    )
