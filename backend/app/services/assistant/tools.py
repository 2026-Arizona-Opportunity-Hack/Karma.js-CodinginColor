"""The assistant's tool registry (AST-2). One entry per supported action.

An entry holds the argument schema the model must follow, the policy action a member needs on
the donor, and the existing endpoint the app calls once the member confirms. Adding a tool
later means one entry here plus a test; nothing else changes."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel

from app.authz.policy import Action
from app.schemas.common import Channel, ContactKind, LongText, ShortText


class NotActionable(Exception):
    """The donor is fine but this action cannot be proposed. The message is shown to the member."""


@dataclass(frozen=True)
class Target:
    """A donor the member may act on, with what a tool needs to build its request."""

    id: int
    name: str
    owner_user_id: int | None
    thank_you_gift_id: int | None  # newest gift that can be thanked, if any


class LogContactArgs(BaseModel):
    donor: ShortText
    kind: ContactKind
    summary: LongText | None = None
    occurred_on: date | None = None


class NextStepArgs(BaseModel):
    donor: ShortText
    title: ShortText
    due_date: date


class ThankYouArgs(BaseModel):
    donor: ShortText
    channel: Channel = "email"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    permission: Action
    method: str
    path: str  # the existing endpoint; {donor_id} is filled per donor
    summary: Callable[[Any, str], str]  # (args, donor label) -> one human-readable line
    body: Callable[[Any, Target], dict[str, Any]]


def _log_body(a: LogContactArgs, _: Target) -> dict[str, Any]:
    return a.model_dump(mode="json", exclude={"donor"}, exclude_none=True)


def _step_body(a: NextStepArgs, _: Target) -> dict[str, Any]:
    return a.model_dump(mode="json", exclude={"donor"})


def _thank_body(a: ThankYouArgs, t: Target) -> dict[str, Any]:
    if t.thank_you_gift_id is None:
        raise NotActionable(f"{t.name} has no gift to thank yet.")
    return {"kind": "thank_you", "channel": a.channel, "gift_id": t.thank_you_gift_id}


def _log_summary(a: LogContactArgs, who: str) -> str:
    when = f" on {a.occurred_on.isoformat()}" if a.occurred_on else ""
    note = f": {a.summary}" if a.summary else ""
    return f"Log a {a.kind} with {who}{when}{note}"


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            name="log_contact",
            description="Record that the member contacted a donor (call, text, email, meeting, note).",  # noqa: E501
            args=LogContactArgs,
            permission=Action.DONOR_ACT,
            method="POST",
            path="/api/app/donors/{donor_id}/interactions",
            summary=_log_summary,
            body=_log_body,
        ),
        Tool(
            name="create_next_step",
            description="Add a follow-up for a donor with a title and a due date (YYYY-MM-DD).",
            args=NextStepArgs,
            permission=Action.DONOR_ACT,
            method="PUT",
            path="/api/app/donors/{donor_id}/next-step",
            summary=lambda a, who: f"Follow up with {who} by {a.due_date.isoformat()}: {a.title}",
            body=_step_body,
        ),
        Tool(
            name="draft_thank_you",
            description="Draft a thank-you message for a donor's latest gift. Never sends it.",
            args=ThankYouArgs,
            permission=Action.DONOR_ACT,
            method="POST",
            path="/api/app/donors/{donor_id}/messages",
            summary=lambda a, who: f"Draft a thank-you {a.channel} to {who} for their latest gift",
            body=_thank_body,
        ),
    )
}

UNSUPPORTED = "I can log a contact, add a follow-up, or draft a thank-you. Try one of those."
EXAMPLES = [
    "Log a call with Maria about the spring gala",
    "Remind me to follow up with Sam next Friday",
    "Draft a thank-you for Priya",
]
