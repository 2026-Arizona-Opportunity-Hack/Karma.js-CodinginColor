"""Built-in message text and merge fields (MSG-1).

Nothing is seeded in the database. A template row is created from these defaults the first
time it is needed, and a board member can then edit it (PUT /templates). Text in
`[EDIT: ...]` marks a spot the person must write; approval refuses while any is left.
"""

import re
from collections.abc import Mapping

ORG_NAME = "Coding in Color"
EDIT_MARKER = "[EDIT:"

MERGE_FIELDS = ("first_name", "gift_amount", "gift_date", "program", "owner_name", "org_name")
TEMPLATE_KINDS = ("thank_you", "quarterly_update", "lapsed_nudge")  # event_invite is later

_FIELD = re.compile(r"\{(\w+)\}")

DEFAULTS: dict[tuple[str, str], tuple[str | None, str]] = {
    ("thank_you", "email"): (
        "Thank you from {org_name}",
        "Hi {first_name},\n\n"
        "Thank you for your gift of {gift_amount} on {gift_date}, supporting {program}. "
        "Gifts like yours let us keep opening doors in tech for people who are too often "
        "left out of it.\n\n"
        "With gratitude,\n{owner_name}\n{org_name}",
    ),
    ("thank_you", "sms"): (
        None,
        "Hi {first_name}, it's {owner_name} from {org_name}. Thank you so much for your "
        "{gift_amount} gift on {gift_date}. It means a lot to us.",
    ),
    ("quarterly_update", "email"): (
        "An update from {org_name}",
        "Hi {first_name},\n\n"
        "I wanted to share a quick update from {org_name} and thank you again for your "
        "support.\n\n"
        "[EDIT: one or two sentences about what the programs did this quarter]\n\n"
        "If you would like to hear more or visit, just reply to this email.\n\n"
        "Warmly,\n{owner_name}\n{org_name}",
    ),
    ("quarterly_update", "sms"): (
        None,
        "Hi {first_name}, it's {owner_name} from {org_name}. "
        "[EDIT: one sentence of news] Thank you for being part of it.",
    ),
    ("lapsed_nudge", "email"): (
        "We would love to see you again at {org_name}",
        "Hi {first_name},\n\n"
        "It has been a while since we last connected, and I wanted to say hello. Your past "
        "support helped {org_name} open doors in tech for people who are too often left out "
        "of it, and I would love to tell you what is happening now.\n\n"
        "If you would like to catch up or visit, just reply to this email.\n\n"
        "Warmly,\n{owner_name}\n{org_name}",
    ),
    ("lapsed_nudge", "sms"): (
        None,
        "Hi {first_name}, it's {owner_name} from {org_name}. We have missed you and would "
        "love to share what your past support made possible. Free to catch up?",
    ),
}


def unknown_fields(text: str) -> list[str]:
    """Placeholders in `text` that are not a merge field (rejected when a template is saved)."""
    return sorted({m for m in _FIELD.findall(text) if m not in MERGE_FIELDS})


def render(text: str, values: Mapping[str, str]) -> str:
    """Replace `{field}` with its value; a field with no value becomes empty text."""
    return _FIELD.sub(lambda m: values.get(m.group(1), ""), text)


def money(cents: int) -> str:
    dollars, rest = divmod(cents, 100)
    return f"${dollars:,}" if rest == 0 else f"${dollars:,}.{rest:02d}"
