"""Imports and the identity review queue. Lane A (Phase 2)."""

from typing import Annotated, Literal

from fastapi import File, Form, Query, UploadFile

from app.routes.stubs import session_router, todo
from app.schemas.common import ErrorOut, ImportSource
from app.schemas.donors import GiftAttributeIn, GiftOut
from app.schemas.imports import (
    ImportBatchOut,
    ImportListOut,
    ImportPreviewOut,
    ReviewDecisionIn,
    ReviewListOut,
    ReviewOut,
)

router = session_router("imports")
FILE_ERRORS: dict[int | str, dict[str, object]] = {
    409: {"model": ErrorOut, "description": "This exact file was already imported (DED-1)"},
    413: {"model": ErrorOut, "description": "File over 5 MB"},
    415: {"model": ErrorOut, "description": "Not a CSV or XLSX file"},
}


@router.post("/imports/preview", responses=FILE_ERRORS)
def preview_import(
    source: Annotated[ImportSource, Form()], file: Annotated[UploadFile, File()]
) -> ImportPreviewOut:
    """Parse, validate, dedupe and classify every row. Writes nothing (ING-4)."""
    todo("lane A, phase 2")


@router.get("/imports")
def list_imports() -> ImportListOut:
    todo("lane A, phase 2")


@router.get("/imports/{batch_id}")
def get_import(batch_id: int) -> ImportBatchOut:
    todo("lane A, phase 2")


@router.post("/imports/{batch_id}/commit", responses={409: {"model": ErrorOut}})
def commit_import(batch_id: int) -> ImportBatchOut:
    """One transaction; blocked when totals do not reconcile (ING-5, ING-9)."""
    todo("lane A, phase 2")


@router.post("/imports/{batch_id}/reverse")
def reverse_import(batch_id: int) -> ImportBatchOut:
    todo("lane A, phase 2")


@router.get("/reviews")
def list_reviews(status: Annotated[Literal["open", "decided"], Query()] = "open") -> ReviewListOut:
    todo("lane A, phase 2")


@router.post("/reviews/{review_id}/decide")
def decide_review(review_id: int, body: ReviewDecisionIn) -> ReviewOut:
    """Link, create new or mark anonymous; the identity is remembered (DED-4)."""
    todo("lane A, phase 2")


@router.post("/gifts/{gift_id}/attribute", responses={409: {"model": ErrorOut}})
def attribute_gift(gift_id: int, body: GiftAttributeIn) -> GiftOut:
    """Only anonymous gifts; pending-review gifts use the review flow (DED-8, issue #71)."""
    todo("lane A, phase 2")
