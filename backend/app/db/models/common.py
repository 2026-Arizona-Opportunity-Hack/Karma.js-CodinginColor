"""Column helpers shared by model modules."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, func
from sqlalchemy.orm import Mapped, mapped_column

TS = DateTime(timezone=True)


def id_col() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(), primary_key=True)


def created_col() -> Mapped[datetime]:
    return mapped_column(TS, server_default=func.now(), nullable=False)
