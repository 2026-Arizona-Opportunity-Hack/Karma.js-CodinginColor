"""Reports. Lane C builds the queries (Phase 2) and A takes the funder export (Phase 4)."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import Query, Response

from app.clock import today
from app.errors import Invalid
from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router
from app.schemas.reports import ReportSummary, RetentionReport
from app.services.reports import funder, retention, summary

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
    donor_id: int,
    cur: CurrentDep,
    db: DB,
    clock: ClockDep,
    format: Annotated[Literal["html", "csv"], Query()] = "html",
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
) -> Response:
    """Any member may export gift history; defaults to the last 12 months."""
    end = to or today(clock)
    start = from_ or end - timedelta(days=364)
    if start > end:
        raise Invalid("The start date must be on or before the end date.")
    x = funder.build(db, cur.actor, donor_id=donor_id, start=start, end=end)
    if format == "csv":
        return Response(
            funder.render_csv(x),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="giving-{donor_id}.csv"'},
        )
    return Response(funder.render_html(x), media_type="text/html")
