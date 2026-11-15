"""Reports. Lane C builds the queries (Phase 2) and A takes the funder export (Phase 4)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import Query, Response

from app.routes.stubs import session_router, todo
from app.schemas.reports import ReportSummary, RetentionReport

router = session_router("reports")


@router.get("/reports/summary")
def report_summary() -> ReportSummary:
    todo("lane C, phase 2")


@router.get("/reports/retention")
def report_retention(
    as_of: Annotated[date | None, Query()] = None,
    basis: Annotated[Literal["rolling", "calendar"], Query()] = "rolling",
) -> RetentionReport:
    todo("lane C, phase 2")


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
