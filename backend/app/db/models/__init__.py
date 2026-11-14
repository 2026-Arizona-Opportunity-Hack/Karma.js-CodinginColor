"""Import every model module here so Alembic and tests see all tables."""

from app.db.models.donors import Donor, DonorIdentity, OwnerHistory
from app.db.models.gifts import Gift, ImportBatch, Program, ProgramOutcome, SourceProgramMap
from app.db.models.imports import ImportRow, MatchReview
from app.db.models.people import ApiKey, AuditLog, Governance, Invite, SessionRow, User
from app.db.models.relationship import (
    AppSetting,
    DigestRun,
    Interaction,
    Message,
    MessageTemplate,
    NextStep,
)

__all__ = [
    "ApiKey",
    "AppSetting",
    "AuditLog",
    "DigestRun",
    "Donor",
    "DonorIdentity",
    "Gift",
    "Governance",
    "ImportBatch",
    "ImportRow",
    "Interaction",
    "Invite",
    "MatchReview",
    "Message",
    "MessageTemplate",
    "NextStep",
    "OwnerHistory",
    "Program",
    "ProgramOutcome",
    "SessionRow",
    "SourceProgramMap",
    "User",
]
