"""Pure normalization functions from DATA_MODEL 3.2."""

import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from openpyxl.utils.datetime import from_excel  # type: ignore[import-untyped]

from app.clock import PHOENIX


def email(value: str) -> str:
    return value.strip().lower()


def phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return digits


def name(value: str) -> str:
    value = re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFKC", value).lower())
    return " ".join(w for w in value.split() if w not in {"mr", "mrs", "ms", "dr"})


def cents(value: object, *, positive: bool = True) -> int:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if value == 0:
        text = "0"
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        amount = Decimal(text)
        if not amount.is_finite():
            raise ValueError("bad_amount")
        result = int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("bad_amount") from exc
    if amount < 0 or result < 0 or (positive and result == 0):
        raise ValueError("non_positive_amount")
    if result > 9_223_372_036_854_775_807:
        raise ValueError("bad_amount")
    return result


def gift_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.astimezone(PHOENIX).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            converted = from_excel(value)
            if isinstance(converted, datetime):
                return converted.date()
        except (ValueError, OverflowError):
            pass
        raise ValueError("bad_date")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError("bad_date")
