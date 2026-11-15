"""Imports and the identity review queue (ING-4 to ING-10, DED-3 to DED-5)."""

from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import CountCents, ImportSource, ImportStatus, MemberRef


class InvalidRow(BaseModel):
    row_number: int
    reason: str


class ImportSummary(BaseModel):
    """rows_read = new + already_imported + needs_review + invalid; must reconcile (ING-5)."""

    rows_read: int
    new_gifts: CountCents
    already_imported: CountCents
    needs_review: CountCents
    invalid: CountCents
    anonymous: CountCents
    new_donors: int
    donors_matched: int
    unmapped_campaigns: list[str] = Field(description="Raw values that fell back to General")
    reconciles: bool


class ImportBatchOut(BaseModel):
    id: int
    source: ImportSource
    filename: str
    status: ImportStatus
    uploaded_by: MemberRef
    created_at: datetime
    committed_at: datetime | None = None
    reversed_at: datetime | None = None
    cutoff_date: date | None = None
    summary: ImportSummary | None = None


class ImportPreviewOut(BaseModel):
    batch: ImportBatchOut
    summary: ImportSummary
    invalid_rows: list[InvalidRow]
    commit_allowed: bool = Field(description="False when totals do not reconcile")


class ImportListOut(BaseModel):
    items: list[ImportBatchOut]


class ReviewCandidate(BaseModel):
    donor_id: int
    display_name: str
    owner: MemberRef | None = None
    match_reason: Literal["email_name_conflict", "phone", "name_employer"]


class ReviewOut(BaseModel):
    id: int
    status: Literal["open", "linked", "created_new", "anonymous"]
    incoming: dict[str, Any] = Field(description="Normalized fields of the incoming record")
    candidates: list[ReviewCandidate]
    file: str | None = None
    row_number: int | None = None
    decided_by: MemberRef | None = None
    decided_at: datetime | None = None


class ReviewListOut(BaseModel):
    items: list[ReviewOut]


class ReviewDecisionIn(BaseModel):
    decision: Literal["link", "create_new", "anonymous"]
    donor_id: int | None = Field(default=None, description="Required when decision is `link`")

    @model_validator(mode="after")
    def link_needs_a_donor(self) -> Self:
        if (self.decision == "link") != (self.donor_id is not None):
            raise ValueError("donor_id is required for `link` and not allowed otherwise")
        return self
