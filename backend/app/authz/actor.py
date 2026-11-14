"""Who is acting. Every repository function takes an Actor (ENGINEERING 2)."""

from dataclasses import dataclass
from typing import Literal

ActorKind = Literal["user", "api_key", "cli", "system"]
ReassignScope = Literal["anyone", "own_only"]


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: int | None
    # True only while this user is the super admin AND the role is active (not dormant).
    is_active_super_admin: bool = False
    # Governance as seen by this request, so the policy needs no database access.
    # super_admin_active is True for every member while a super admin is active (GOV-4).
    super_admin_active: bool = False
    reassign_scope: ReassignScope = "anyone"
    ip: str | None = None

    @property
    def user_id(self) -> int | None:
        return self.id if self.kind == "user" else None


CLI = Actor(kind="cli", id=None)
SYSTEM = Actor(kind="system", id=None)
