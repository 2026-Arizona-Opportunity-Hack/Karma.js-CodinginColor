"""Reports. Lane C builds the queries (Phase 2) and A takes the funder export (Phase 4)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import Query, Response

from app.clock import today
from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router, todo
from app.schemas.reports import ReportSummary, RetentionReport
from app.services.reports import retention, summary

router = session_router("reports")


@router.get("/reports/summary")
def report_summary(cur: CurrentDep, db: DB, clock: ClockDep) -> ReportSummary:
    return summary.build(db, clock, cur.actor)


@router.get("/reports/retention")
def report_retention(
    cur: CurrentDep,
    db: DB,
    clock: ClockDep,
    as_of: Annotated[date | None, Query()] = None,
    basis: Annotated[Literal["rolling", "calendar"], Query()] = "rolling",
) -> RetentionReport:
    result = retention.build(db, cur.actor, as_of=as_of or today(clock), basis=basis)
    return retention.to_app_report(result)


@router.get(
    "/reports/funder/{donor_id}",
    response_class=Response,
    responses={
        200: {
            "description": "Printable HTML, or CSV with formulas neutralized (DON-12, RPT-3)",
            "content": {"text/html": {}, "text/csv": {}},
        }
    },
)
def funder_export(
    donor_id: int, format: Annotated[Literal["html", "csv"], Query()] = "html"
) -> Response:
    todo("lane A, phase 4")
