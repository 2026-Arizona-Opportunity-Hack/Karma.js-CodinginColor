"""Imports and the identity review queue. Lane A (Phase 2)."""

from typing import Annotated, Literal

from fastapi import File, Form, Query, UploadFile

from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router
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
from app.services.dedupe import attribution, reviews
from app.services.ingest import batches, service
from app.services.ingest.uploads import MAX_BYTES

router = session_router("imports")
FILE_ERRORS: dict[int | str, dict[str, object]] = {
    409: {"model": ErrorOut, "description": "This exact file was already imported (DED-1)"},
    413: {"model": ErrorOut, "description": "File over 5 MB"},
    415: {"model": ErrorOut, "description": "Not a CSV or XLSX file"},
}


@router.post("/imports/preview", responses=FILE_ERRORS)
def preview_import(
    source: Annotated[ImportSource, Form()],
    file: Annotated[UploadFile, File()],
    db: DB,
    cur: CurrentDep,
    clock: ClockDep,
) -> ImportPreviewOut:
    """Parse, validate, dedupe and classify every row. Writes nothing (ING-4)."""
    return service.preview(
        db, cur.actor, clock, source, file.filename or "upload", file.file.read(MAX_BYTES + 1)
    )


@router.get("/imports")
def list_imports(db: DB, cur: CurrentDep) -> ImportListOut:
    return batches.list_batches(db, cur.actor)


@router.get("/imports/{batch_id}")
def get_import(batch_id: int, db: DB, cur: CurrentDep, clock: ClockDep) -> ImportBatchOut:
    return batches.get(db, cur.actor, clock, batch_id)


@router.post("/imports/{batch_id}/commit", responses={409: {"model": ErrorOut}})
def commit_import(batch_id: int, db: DB, cur: CurrentDep, clock: ClockDep) -> ImportBatchOut:
    """One transaction; blocked when totals do not reconcile (ING-5, ING-9)."""
    return batches.commit(db, cur.actor, clock, batch_id)


@router.post("/imports/{batch_id}/reverse")
def reverse_import(batch_id: int, db: DB, cur: CurrentDep, clock: ClockDep) -> ImportBatchOut:
    return batches.reverse(db, cur.actor, clock, batch_id)


@router.get("/reviews")
def list_reviews(
    db: DB, cur: CurrentDep, status: Annotated[Literal["open", "decided"], Query()] = "open"
) -> ReviewListOut:
    return reviews.list_reviews(db, cur.actor, status)


@router.post("/reviews/{review_id}/decide")
def decide_review(
    review_id: int, body: ReviewDecisionIn, db: DB, cur: CurrentDep, clock: ClockDep
) -> ReviewOut:
    """Link, create new or mark anonymous; the identity is remembered (DED-4)."""
    return reviews.decide(db, cur.actor, clock, review_id, body)


@router.post("/gifts/{gift_id}/attribute", responses={409: {"model": ErrorOut}})
def attribute_gift(
    gift_id: int, body: GiftAttributeIn, db: DB, cur: CurrentDep, clock: ClockDep
) -> GiftOut:
    """Only anonymous gifts; pending-review gifts use the review flow (DED-8, issue #71).

    A Benevity gift that is anonymous is refused with 409 ("This donor chose to stay anonymous;
    the gift stays unattributed."): the donor opted out, so it never gets a donor (D-131). It
    still counts in org revenue and reports. Anonymous gifts from other sources stay attributable.
    """
    return attribution.attribute(db, cur.actor, clock, gift_id, body.donor_id)
