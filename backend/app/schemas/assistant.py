"""Assistant: the model proposes, the member confirms (AST-1). Nothing here writes."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

AssistantText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class InterpretIn(BaseModel):
    text: AssistantText


class ProposedRequest(BaseModel):
    """The existing endpoint to call on Confirm. Same call the matching screen makes."""

    method: Literal["POST", "PUT"]
    path: str
    body: dict[str, Any]


class DonorChoice(BaseModel):
    donor_id: int
    donor_name: str
    request: ProposedRequest


class ProposedAction(BaseModel):
    tool: Literal["log_contact", "create_next_step", "draft_thank_you"]
    summary: str
    status: Literal["ready", "choose_donor", "error"] = Field(
        description="ready: one donor. choose_donor: pick one of `choices`. error: see `error`."
    )
    choices: list[DonorChoice] = Field(
        default=[], description="One entry when ready, several when the name is ambiguous"
    )
    error: str | None = None


class InterpretOut(BaseModel):
    actions: list[ProposedAction]
    message: str | None = Field(
        default=None, description="A question from the model, or what is supported"
    )
    examples: list[str]
