"""Imports and the identity review queue (ING-4 to ING-10, DED-3 to DED-5)."""

from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import CountCents, ImportSource, ImportStatus, MemberRef


class InvalidRow(BaseModel):
    row_number: int
    reason: str


class ImportClassSummary(CountCents):
    """Physical source rows, independently counted gifts, and gross USD cents."""

    count: int = Field(ge=0, description="Physical source rows in this class")
    cents: int = Field(ge=0, description="Donation cents plus employer-match cents")
    gift_count: int = Field(
        ge=0, description="Gifts represented by these rows; donor-only rows add 0"
    )
    donation_cents: int = Field(ge=0)
    match_cents: int = Field(ge=0)

    @model_validator(mode="after")
    def cents_equal_components(self) -> Self:
        if self.cents != self.donation_cents + self.match_cents:
            raise ValueError("cents must equal donation_cents + match_cents")
        return self


class ImportSummary(BaseModel):
    """Reconcile physical rows and gross cents independently (ING-5, D-127).

    Anonymous is a subset of new rows; it is excluded from the conservation sum.
    Invalid rows contribute no accepted gifts or cents. Counts include donor-only
    spreadsheet rows; gift_count never counts those as gifts.
    """

    rows_read: int = Field(ge=0)
    gift_count: int = Field(
        ge=0, description="Parsed valid gifts, including matches and review gifts"
    )
    donation_cents: int = Field(ge=0)
    match_cents: int = Field(ge=0)
    total_cents: int = Field(ge=0, description="Gross donation plus match cents before fees")
    new_gifts: ImportClassSummary
    already_imported: ImportClassSummary
    needs_review: ImportClassSummary
    invalid: ImportClassSummary
    anonymous: ImportClassSummary
    new_donors: int
    donors_matched: int
    unmapped_campaigns: list[str] = Field(description="Raw values that fell back to General")
    rows_reconcile: bool = False
    cents_reconcile: bool = False
    reconciles: bool = False

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        classes = (self.new_gifts, self.already_imported, self.needs_review, self.invalid)
        self.rows_reconcile = self.rows_read == sum(c.count for c in classes)
        self.cents_reconcile = (
            self.total_cents
            == self.donation_cents + self.match_cents
            == sum(c.cents for c in classes)
            and self.donation_cents == sum(c.donation_cents for c in classes)
            and self.match_cents == sum(c.match_cents for c in classes)
        )
        anonymous_is_subset = all(
            getattr(self.anonymous, key) <= getattr(self.new_gifts, key)
            for key in ("count", "cents", "gift_count", "donation_cents", "match_cents")
        )
        self.reconciles = (
            self.rows_reconcile
            and self.cents_reconcile
            and anonymous_is_subset
            and self.gift_count == sum(c.gift_count for c in classes)
        )
        return self


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
