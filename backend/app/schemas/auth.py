from typing import Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class GovernanceOut(BaseModel):
    mode: Literal["flat", "super_admin"]
    reassign_scope: Literal["anyone", "own_only"]


class MeOut(BaseModel):
    id: int
    email: str
    display_name: str
    is_super_admin: bool
    governance: GovernanceOut
