"""Turn one sentence into proposed actions. Never writes donor data (AST-1)."""

import json
import re
from typing import Any, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import can
from app.clock import PHOENIX, Clock
from app.errors import NotFound, TooManyRequests, Unavailable
from app.repos import assistant as repo
from app.repos import audit
from app.repos.donors import OwnedBy
from app.schemas.assistant import DonorChoice, InterpretOut, ProposedAction, ProposedRequest
from app.services.ai.gateway import Gateway, GatewayError
from app.services.apikeys import ratelimit
from app.services.assistant.tools import EXAMPLES, TOOLS, UNSUPPORTED, NotActionable, Target, Tool

RATE_LIMIT = 20  # per member per minute
MAX_ACTIONS = 5
UNAVAILABLE = "The assistant is not available right now. You can still use the forms."


class _RawAction(BaseModel):
    tool: str
    args: dict[str, Any] = {}


class _Reply(BaseModel):
    actions: list[_RawAction] = []


def system_prompt(today: str, weekday: str) -> str:
    schemas: dict[str, Any] = {
        name: {"description": t.description, "args": t.args.model_json_schema()}
        for name, t in TOOLS.items()
    }
    schemas["unclear"] = {
        "description": "Use when the request is ambiguous; ask one short question.",
        "args": {"question": "string"},
    }
    return (
        "You turn one sentence from a nonprofit staff member into actions for a donor app. "
        f"Today is {weekday} {today} (America/Phoenix); write dates as YYYY-MM-DD. "
        "Reply with JSON only, no prose: "
        '{"actions": [{"tool": "<name>", "args": {...}}]}. One action per intent, at most '
        f"{MAX_ACTIONS}. Put the donor's name exactly as spoken in `donor`. Tools: "
        + json.dumps(schemas, separators=(",", ":"))
    )


def _parse(raw: str) -> _Reply:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        return _Reply.model_validate(json.loads(s))
    except ValueError:  # includes pydantic's ValidationError
        raise GatewayError("unusable reply") from None


def _action(tool: Tool, summary: str, status: str, **kw: Any) -> ProposedAction:
    return ProposedAction(tool=tool.name, summary=summary, status=status, **kw)


def _propose(
    db: Session, actor: Actor, clock: Clock, tool: Tool, raw: dict[str, Any]
) -> ProposedAction | None:
    """None when the model's arguments do not fit the tool's schema."""
    try:
        args = tool.args.model_validate(raw)
    except ValidationError:
        return None
    name = cast(str, getattr(args, "donor"))  # noqa: B009
    today = clock.now().astimezone(PHOENIX).date()
    found: list[Target] = [
        t
        for t in repo.find_targets(db, actor, name, today=today)
        if can(actor, tool.permission, OwnedBy(t.owner_user_id))
    ]
    exact = [t for t in found if t.name.lower() == name.lower()]
    if len(exact) == 1:
        found = exact
    if not found:
        return _action(
            tool, tool.summary(args, name), "error",
            error=f"I could not find a donor of yours called “{name}”.",
        )  # fmt: skip

    choices: list[DonorChoice] = []
    problem = ""
    for t in found:
        try:
            req = ProposedRequest(
                method=tool.method,
                path=tool.path.format(donor_id=t.id),
                body=tool.body(args, t),
            )
        except NotActionable as e:
            problem = str(e)
            continue
        choices.append(DonorChoice(donor_id=t.id, donor_name=t.name, request=req))
    if not choices:
        return _action(tool, tool.summary(args, name), "error", error=problem)
    if len(choices) == 1:
        return _action(tool, tool.summary(args, choices[0].donor_name), "ready", choices=choices)
    return _action(tool, tool.summary(args, name), "choose_donor", choices=choices)


def interpret(db: Session, clock: Clock, actor: Actor, gateway: Gateway, text: str) -> InterpretOut:
    if not repo.is_enabled(db):
        raise NotFound("Not found.")
    wait = ratelimit.check(f"assistant:{actor.id}", clock.now(), RATE_LIMIT)
    if wait is not None:
        raise TooManyRequests(
            f"The assistant allows {RATE_LIMIT} requests per minute.",
            headers={"Retry-After": str(wait)},
        )
    today = clock.now().astimezone(PHOENIX).date()
    prompt = system_prompt(today.isoformat(), today.strftime("%A"))
    try:
        reply = _parse(gateway.complete(prompt, text))
    except GatewayError:
        raise Unavailable(UNAVAILABLE) from None

    actions: list[ProposedAction] = []
    messages: list[str] = []
    for raw in reply.actions[:MAX_ACTIONS]:
        if raw.tool == "unclear":
            q = raw.args.get("question")
            if isinstance(q, str) and q.strip():
                messages.append(q.strip()[:300])
        elif raw.tool in TOOLS:
            proposed = _propose(db, actor, clock, TOOLS[raw.tool], raw.args)
            if proposed is None:
                messages.append("I did not catch all the details. Could you rephrase that?")
            else:
                actions.append(proposed)
        elif UNSUPPORTED not in messages:  # any tool we do not offer, including find_donor
            messages.append(UNSUPPORTED)
    if not actions and not messages:
        messages.append(UNSUPPORTED)
    # Which tools were proposed, never the sentence (AST-3).
    audit.write(db, actor, "assistant.interpret", data={"actions": [a.tool for a in actions]})
    return InterpretOut(actions=actions, message=" ".join(messages) or None, examples=EXAMPLES)
