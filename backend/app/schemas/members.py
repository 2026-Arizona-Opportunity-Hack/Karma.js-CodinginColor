"""Members, invites and governance (AUTH-4, GOV-4, GOV-5, OWN-3 bulk move)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Email, MemberRef, ReassignScope


class MemberOut(BaseModel):
    id: int
    email: str
    display_name: str
    is_active: bool
    is_super_admin: bool
    owned_donor_count: int
    created_at: datetime
    deactivated_at: datetime | None = None


class MemberListOut(BaseModel):
    items: list[MemberOut]


class InviteIn(BaseModel):
    email: Email


class InviteOut(BaseModel):
    id: int
    email: str
    invite_url: str = Field(description="Shown once; the server stores only a hash")
    expires_at: datetime


class InviteAcceptIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)


class MoveDonorsIn(BaseModel):
    to_user_id: int


class MoveDonorsOut(BaseModel):
    moved: int


class GovernanceDetail(BaseModel):
    mode: Literal["flat", "super_admin"]
    super_admin_state: Literal["none", "active", "dormant"]
    reassign_scope: ReassignScope
    super_admin: MemberRef | None = None
    updated_at: datetime


class ScopeIn(BaseModel):
    reassign_scope: ReassignScope
