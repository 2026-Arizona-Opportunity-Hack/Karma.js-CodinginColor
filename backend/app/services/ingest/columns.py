"""Map spreadsheet columns to custom fields and report the rest as ignored (ING-14, CUS-4).

A column imports into a field when its normalized header equals the normalized label or key of an
active custom field. Built-in columns keep their own handling in the adapters; every other
unmatched column is listed in the preview so the person can create a field from it.
"""

import re
from datetime import date, datetime
from typing import Any

from app.db.models import FieldDefinition
from app.schemas.common import ImportSource
from app.schemas.imports import IgnoredColumn
from app.services.fields import values
from app.services.ingest import normalizers
from app.services.ingest.uploads import has_value

# Headers each adapter already reads (normalized with `adapters.header`).
KNOWN: dict[str, set[str]] = {
    "spreadsheet": {
        "name", "first name", "last name", "type", "organization", "email", "phone", "notes",
        "contact id",
    },
    "zeffy": {
        "payment id", "date", "amount", "payment status", "currency", "refunded amount",
        "first name", "last name", "email", "phone", "organization", "contact id", "campaign",
    },
    "benevity": {
        "transaction id", "donation date", "donation amount", "donation currency",
        "disbursement id", "disbursement date", "cause support fee", "merchant fee",
        "project name", "company name", "match amount", "donor first name", "donor last name",
        "donor email",
    },
    "generic": {
        "date", "amount", "platform", "fee", "campaign", "donor name", "email", "phone",
        "organization", "transaction id",
    },
}  # fmt: skip
_BOOL_WORDS = {"true", "false", "yes", "no", "y", "n"}


def norm(value: object) -> str:
    return re.sub(r"[\s_-]+", " ", str(value or "").strip().lower())


def mapping(
    source: ImportSource, headers: list[str], fields: list[FieldDefinition]
) -> dict[str, FieldDefinition]:
    """Normalized header -> the active custom field it fills (spreadsheets: donor fields only)."""
    by_name: dict[str, FieldDefinition] = {}
    for d in fields:
        if d.is_builtin or not d.is_active or (source == "spreadsheet" and d.entity != "donor"):
            continue
        by_name.setdefault(norm(d.label), d)
        by_name.setdefault(norm(d.key), d)
    return {h: by_name[h] for h in headers if h and h not in KNOWN[source] and h in by_name}


def cell(defn: FieldDefinition, raw: Any) -> Any:
    """Canonical stored value for one spreadsheet cell, or ValueError naming the field."""
    if isinstance(raw, datetime):
        raw = raw.date()
    if defn.type in ("text", "long_text", "choice") and not isinstance(raw, str):
        raw = raw.isoformat() if isinstance(raw, date) else str(raw)
    elif defn.type == "money" and isinstance(raw, float):
        raw = str(raw)
    elif defn.type == "date" and isinstance(raw, date):
        return raw.isoformat()
    try:
        return values.parse(defn, raw)
    except ValueError as exc:
        raise ValueError(f"{defn.label}: {exc}") from exc


def read_custom(
    row: dict[str, object], mapped: dict[str, FieldDefinition]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(donor values, gift values) from one row. A bad value raises ValueError."""
    donor: dict[str, Any] = {}
    gift: dict[str, Any] = {}
    for name, defn in mapped.items():
        raw = row.get(name)
        if not has_value(raw):
            continue
        (donor if defn.entity == "donor" else gift)[defn.key] = cell(defn, raw)
    return donor, gift


def _is_date(text: str) -> bool:
    try:
        normalizers.gift_date(text)
    except ValueError:
        return False
    return True


def _is_number(text: str) -> bool:
    try:
        float(text.replace(",", ""))
    except ValueError:
        return False
    return True


def _guess(samples: list[object]) -> str:
    """Best type for a column from its first values; text when unsure."""
    if not samples:
        return "text"
    texts = [str(s).strip() for s in samples]
    if all(t.lower() in _BOOL_WORDS for t in texts):
        return "bool"
    if all(isinstance(s, (date, datetime)) for s in samples) or all(_is_date(t) for t in texts):
        return "date"
    if all(_is_number(t) for t in texts):
        return "number"
    return "long_text" if any(len(t) > 200 for t in texts) else "text"


def ignored(
    source: ImportSource,
    headers: list[object],
    rows: list[list[object]],
    mapped: dict[str, FieldDefinition],
) -> list[IgnoredColumn]:
    out: list[IgnoredColumn] = []
    for index, raw_header in enumerate(headers):
        name = norm(raw_header)
        if not name or name in KNOWN[source] or name in mapped:
            continue
        samples = [r[index] for r in rows[:50] if index < len(r) and has_value(r[index])]
        out.append(
            IgnoredColumn(
                header=str(raw_header).strip(),
                guessed_type=_guess(samples),
                suggested_entity="donor" if source == "spreadsheet" else "gift",
            )
        )
    return out
