"""Field definitions for donors and gifts (CUS-1, DATA_MODEL 2.1). Values live in `custom`."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TS, created_col, id_col

FIELD_TYPES = ("text", "long_text", "number", "money", "date", "bool", "choice", "multi_choice")


class FieldDefinition(Base):
    """One field on donors or gifts. Built-ins map to real columns and are never deleted,
    retyped or re-keyed; custom values are stored in `donors.custom` / `gifts.custom`."""

    __tablename__ = "field_definitions"
    __table_args__ = (
        CheckConstraint("entity IN ('donor','gift')", name="entity"),
        CheckConstraint(
            "type IN ('text','long_text','number','money','date','bool','choice','multi_choice')",
            name="type",
        ),
        UniqueConstraint("entity", "key", name="uq_field_definitions_entity_key"),
    )

    id: Mapped[int] = id_col()
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    choices: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    is_builtin: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    is_required: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    is_contact: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    show_in_list: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=text("now()"), nullable=False)
