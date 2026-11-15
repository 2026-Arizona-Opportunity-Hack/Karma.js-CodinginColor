"""Field definitions and the metadata that travels with custom values (CUS-1, CUS-4)."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

FieldType = Literal[
    "text", "long_text", "number", "money", "date", "bool", "choice", "multi_choice"
]
Entity = Literal["donor", "gift"]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Choice = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Custom = dict[str, Any]


class FieldMeta(BaseModel):
    """Enough to render a custom value: sent beside `custom` on donor and gift reads."""

    key: str
    label: str
    type: FieldType
    choices: list[str] | None = None
    position: int
    is_required: bool = False
    is_builtin: bool = False
    is_contact: bool = False


class FieldOut(FieldMeta):
    id: int
    entity: Entity
    show_in_list: bool
    is_active: bool
    has_values: bool = Field(description="True when any record holds a value (blocks delete)")


class FieldListOut(BaseModel):
    items: list[FieldOut]


class FieldCreate(BaseModel):
    entity: Entity
    label: Label
    type: FieldType
    choices: list[Choice] | None = Field(default=None, max_length=50)
    is_required: bool = False
    is_contact: bool = Field(default=False, description="Values follow DON-3. Fixed after creation")
    show_in_list: bool = False


class FieldPatch(BaseModel):
    """Key, type, entity and the contact flag never change. Built-ins accept only label,
    position, show_in_list and is_active."""

    label: Label | None = None
    choices: list[Choice] | None = Field(default=None, max_length=50)
    position: int | None = Field(default=None, ge=0, le=100_000)
    show_in_list: bool | None = None
    is_required: bool | None = None
    is_active: bool | None = None
