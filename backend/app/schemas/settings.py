"""Settings, templates, programs, program map, outcomes and API keys (GOV-4, REM-7, MSG-1)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Channel, ImportSource, MessageKind, ShortText


class SettingsOut(BaseModel):
    thank_you_days_first: int
    thank_you_days_repeat: int
    quarterly_days: int
    import_cutoff_days: int
    retention_basis: Literal["rolling", "calendar"]


class SettingsIn(BaseModel):
    thank_you_days_first: int | None = Field(default=None, ge=0, le=60)
    thank_you_days_repeat: int | None = Field(default=None, ge=0, le=90)
    quarterly_days: int | None = Field(default=None, ge=7, le=365)
    import_cutoff_days: int | None = Field(default=None, ge=0, le=3650)
    retention_basis: Literal["rolling", "calendar"] | None = None


class TemplateOut(BaseModel):
    id: int
    kind: MessageKind
    channel: Channel
    subject: str | None = None
    body: str
    merge_fields: list[str]
    updated_at: datetime


class TemplateListOut(BaseModel):
    items: list[TemplateOut]


class TemplateIn(BaseModel):
    kind: MessageKind
    channel: Channel
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class ProgramOut(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool


class ProgramListOut(BaseModel):
    items: list[ProgramOut]


class ProgramCreate(BaseModel):
    name: ShortText


class ProgramUpdate(BaseModel):
    name: ShortText | None = None
    is_active: bool | None = None


class ProgramMapEntry(BaseModel):
    id: int
    source: ImportSource
    source_value: str
    program: ProgramOut


class ProgramMapListOut(BaseModel):
    items: list[ProgramMapEntry]


class ProgramMapIn(BaseModel):
    source: ImportSource
    source_value: ShortText
    program_id: int


class OutcomeOut(BaseModel):
    id: int
    program: ProgramOut
    period_start: date
    period_end: date
    metric_label: str
    value: Decimal
    unit: str
    source_note: str | None = None


class OutcomeListOut(BaseModel):
    items: list[OutcomeOut]


class OutcomeIn(BaseModel):
    program_id: int
    period_start: date
    period_end: date
    metric_label: ShortText
    value: Decimal
    unit: ShortText
    source_note: str | None = Field(default=None, max_length=500)


class ApiKeyOut(BaseModel):
    id: int
    name: str
    type: Literal["read_only", "full_access"]
    prefix: str = Field(description="First characters, for recognising a key")
    scopes: list[str]
    created_by: int
    created_by_name: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = Field(default=None, description="None = never expires")
    revoked_at: datetime | None = None


class ApiKeyListOut(BaseModel):
    items: list[ApiKeyOut]


class ApiKeyCreate(BaseModel):
    name: ShortText
    scopes: list[Literal["read:aggregates", "full_access"]] = Field(
        default=["read:aggregates"],
        min_length=1,
        description="`full_access` reads and changes everything on /api/app and stands alone.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Omit for the default (90 days for full_access, never for read-only); "
        "send null for never.",
    )


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="The full key. Shown once; only a hash is stored.")
