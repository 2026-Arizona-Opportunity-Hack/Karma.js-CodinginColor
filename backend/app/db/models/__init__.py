"""Import every model module here so Alembic and tests see all tables."""

from app.db.models.donors import Donor, DonorIdentity, OwnerHistory
from app.db.models.gifts import Gift, ImportBatch, Program, ProgramOutcome, SourceProgramMap
from app.db.models.people import ApiKey, AuditLog, Governance, Invite, SessionRow, User

__all__ = [
    "ApiKey",
    "AuditLog",
    "Donor",
    "DonorIdentity",
    "Gift",
    "Governance",
    "ImportBatch",
    "Invite",
    "OwnerHistory",
    "Program",
    "ProgramOutcome",
    "SessionRow",
    "SourceProgramMap",
    "User",
]
