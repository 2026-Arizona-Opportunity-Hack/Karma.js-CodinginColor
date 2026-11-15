"""Validate and shape custom field values (CUS-1 to CUS-4).

Values are checked by type on every write, whether they arrive from the API, manual entry or an
import. Stored forms: text and long_text as strings, number as int or float, money as integer
cents, date as ISO text, bool as true/false, choice as one string, multi_choice as a list.
Text from forms and spreadsheets is accepted too: `$25.50`, `3/4/2026`, `yes`.
"""

import math
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from app.db.models import FieldDefinition
from app.errors import Unprocessable
from app.services.ingest import normalizers

SHORT_MAX, LONG_MAX = 500, 5000
_TRUE, _FALSE = {"true", "yes", "y", "1"}, {"false", "no", "n", "0"}


def _empty(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip()) or raw == []


def parse(defn: FieldDefinition, raw: Any) -> Any:
    """Return the canonical stored value, or raise ValueError with a short reason."""
    kind = defn.type
    if kind in ("text", "long_text"):
        if not isinstance(raw, str):
            raise ValueError("must be text")
        value, limit = raw.strip(), (LONG_MAX if kind == "long_text" else SHORT_MAX)
        if len(value) > limit:
            raise ValueError(f"must be at most {limit} characters")
        return value
    if kind == "number":
        if isinstance(raw, bool):
            raise ValueError("must be a number")
        try:
            num = raw if isinstance(raw, (int, float)) else float(str(raw).replace(",", ""))
        except ValueError:
            raise ValueError("must be a number") from None
        if not math.isfinite(num):
            raise ValueError("must be a number")
        return int(num) if float(num).is_integer() and abs(num) < 2**53 else num
    if kind == "money":
        if isinstance(raw, (bool, float)):
            raise ValueError("must be whole cents, for example 2550, or text like $25.50")
        try:
            return (
                raw if isinstance(raw, int) and raw >= 0 else normalizers.cents(raw, positive=False)
            )
        except ValueError:
            raise ValueError("must be an amount of money, zero or more") from None
    if kind == "date":
        try:
            return (
                normalizers.gift_date(raw).isoformat()
                if not isinstance(raw, (int, float))
                else _bad()
            )
        except ValueError:
            raise ValueError("must be a date such as 2026-11-15") from None
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        word = str(raw).strip().lower()
        if word in _TRUE:
            return True
        if word in _FALSE:
            return False
        raise ValueError("must be yes or no")
    if kind == "choice":
        if not isinstance(raw, str) or raw.strip() not in (defn.choices or []):
            raise ValueError(f"must be one of: {', '.join(defn.choices or [])}")
        return raw.strip()
    if kind == "multi_choice":
        items = raw if isinstance(raw, list) else [p for p in str(raw).split(";") if p.strip()]
        picked = [str(i).strip() for i in items]
        bad = [i for i in picked if i not in (defn.choices or [])]
        if bad:
            raise ValueError(f"{', '.join(bad)} is not one of: {', '.join(defn.choices or [])}")
        return list(dict.fromkeys(picked))
    raise ValueError("unknown field type")


def _bad() -> date:
    raise ValueError("bad_date")


def validate(
    defs: Iterable[FieldDefinition],
    incoming: Mapping[str, Any],
    existing: Mapping[str, Any] | None = None,
    *,
    creating: bool = False,
) -> dict[str, Any]:
    """Merge `incoming` over `existing` and return the new `custom` object.

    `null` or an empty value clears a field. Unknown, built-in and deactivated keys are refused,
    and every message starts with the field's label so the person knows which one to fix."""
    by_key = {d.key: d for d in defs}
    merged = dict(existing or {})
    for key, raw in incoming.items():
        defn = by_key.get(key)
        if defn is None:
            raise Unprocessable(f"Unknown field '{key}'.")
        if defn.is_builtin:
            raise Unprocessable(f"{defn.label} is a built-in field. Send it as '{key}' directly.")
        if not defn.is_active:
            raise Unprocessable(f"{defn.label} is deactivated. Restore it to change its value.")
        if _empty(raw):
            merged.pop(key, None)
            continue
        try:
            merged[key] = parse(defn, raw)
        except ValueError as exc:
            raise Unprocessable(f"{defn.label}: {exc}.") from exc
    for defn in by_key.values():
        if defn.is_builtin or not defn.is_active or not defn.is_required:
            continue
        if (creating or defn.key in incoming) and defn.key not in merged:
            raise Unprocessable(f"{defn.label} is required.")
    return merged


def visible(
    defs: Iterable[FieldDefinition], custom: Mapping[str, Any], *, can_see_contact: bool
) -> dict[str, Any]:
    """Values the viewer may see: active fields only, contact fields only with DON-3 access."""
    return {
        d.key: custom[d.key]
        for d in defs
        if d.key in custom
        and d.is_active
        and not d.is_builtin
        and (can_see_contact or not d.is_contact)
    }
