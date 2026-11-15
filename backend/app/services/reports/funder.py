"""Funder export (RPT-3, DON-12): a donor's own giving by program and year, plus the outcomes
entered for those programs, as printable HTML or CSV.

Employer matches are not the donor's own giving (D-127), so they are left out and the export says
so. Email, phone and notes appear only when the actor may see them (DON-3, D-129). Every export
writes an audit entry, every CSV cell that could run as a formula is neutralized, and every HTML
value is escaped."""

import csv
import io
from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.repos import audit, funder, outcomes

MATCH_NOTE = (
    "Employer matching gifts are not included in this donor's giving "
    "(they are counted in organization revenue only)."
)
CSV_COLUMNS = [
    "section",
    "program",
    "period",
    "gifts",
    "amount_usd",
    "metric",
    "value",
    "unit",
    "note",
]


@dataclass
class Export:
    donor_name: str
    start: date
    end: date
    gifts: list[dict[str, Any]]
    total_cents: int
    excluded: dict[str, int]
    outcomes: list[dict[str, str]]
    contact: dict[str, str] | None


def usd(cents: int) -> str:
    return f"{cents // 100:,}.{cents % 100:02d}"


def safe_cell(value: object) -> str:
    """Spreadsheet programs run cells starting with = + - @ (or tab/CR) as formulas (DON-12)."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def build(db: Session, actor: Actor, *, donor_id: int, start: date, end: date) -> Export:
    donor = funder.donor_for_export(db, actor, donor_id)
    gifts = funder.gift_lines(db, actor, donor_id=donor.id, start=start, end=end)
    program_ids = sorted({g["program_id"] for g in gifts})
    found = outcomes.for_programs(db, actor, program_ids=program_ids, start=start, end=end)
    contact = None
    if can(actor, Action.DONOR_VIEW_CONTACT, donor):
        contact = {
            "Email": donor.email or "",
            "Phone": donor.phone or "",
            "Notes": donor.notes or "",
        }
    audit.write(
        db, actor, "report.funder_export", entity="donor", entity_id=donor.id,
        data={
            "from": start.isoformat(),
            "to": end.isoformat(),
            "contact_included": contact is not None,
        },
    )  # fmt: skip
    return Export(
        donor_name=donor.display_name,
        start=start,
        end=end,
        gifts=gifts,
        total_cents=sum(g["cents"] for g in gifts),
        excluded=funder.excluded_matches(db, actor, donor_id=donor.id, start=start, end=end),
        outcomes=[
            {
                "program": p.name,
                "period": f"{o.period_start} to {o.period_end}",
                "metric": o.metric_label,
                "value": f"{o.value.normalize():f}",
                "unit": o.unit,
                "note": o.source_note or "",
            }
            for o, p in found
        ],
        contact=contact,
    )


def render_csv(x: Export) -> str:
    n_gifts = sum(g["gifts"] for g in x.gifts)
    e = ""
    rows: list[list[object]] = [["donor", x.donor_name, f"{x.start} to {x.end}", e, e, e, e, e, e]]
    rows += [
        ["gifts", g["program"], g["year"], g["gifts"], usd(g["cents"]), e, e, e, e] for g in x.gifts
    ]
    rows.append(["total", e, e, n_gifts, usd(x.total_cents), e, e, e, e])
    rows += [
        ["outcome", o["program"], o["period"], e, e, o["metric"], o["value"], o["unit"], o["note"]]
        for o in x.outcomes
    ]
    rows.append(["note", e, e, e, e, e, e, e, MATCH_NOTE])
    if x.excluded["gifts"]:
        rows.append(
            ["excluded_matches", e, e, x.excluded["gifts"], usd(x.excluded["cents"]), e, e, e, e]
        )
    rows += [["contact", k, e, e, e, e, e, e, v] for k, v in (x.contact or {}).items()]
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    for r in rows:
        w.writerow([safe_cell(c) for c in r])
    return out.getvalue()


def _table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th scope='col'>{escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(x: Export) -> str:
    n_gifts = sum(g["gifts"] for g in x.gifts)
    gifts = _table(
        ["Program", "Year", "Gifts", "Amount (USD)"],
        [[g["program"], g["year"], g["gifts"], usd(g["cents"])] for g in x.gifts]
        + [["Total", "", n_gifts, usd(x.total_cents)]],
    )
    if x.outcomes:
        outs = _table(
            ["Program", "Period", "Outcome", "Value", "Unit", "Source"],
            [
                [o["program"], o["period"], o["metric"], o["value"], o["unit"], o["note"]]
                for o in x.outcomes
            ],
        )
    else:
        outs = "<p>No outcomes have been entered for these programs and dates.</p>"
    excluded = ""
    if x.excluded["gifts"]:
        excluded = (
            f"<p>Left out: {x.excluded['gifts']} employer matching gift(s), "
            f"${usd(x.excluded['cents'])}.</p>"
        )
    contact = ""
    if x.contact:
        items = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in x.contact.items())
        contact = f"<h2>Contact</h2><dl>{items}</dl>"
    name = escape(x.donor_name)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>Giving summary: {name}</title>"
        "<style>body{font:16px/1.5 system-ui,sans-serif;margin:2rem auto;max-width:48rem;"
        "padding:0 1rem}table{border-collapse:collapse;width:100%;margin:1rem 0}"
        "th,td{border:1px solid #444;padding:.4rem;text-align:left}"
        "@media print{body{margin:0}}</style></head><body>"
        f"<h1>Giving summary: {name}</h1><p>{x.start} to {x.end}</p>"
        f"<h2>Gifts by program</h2>{gifts}<p>{escape(MATCH_NOTE)}</p>{excluded}"
        f"<h2>Funded outcomes</h2>{outs}{contact}</body></html>"
    )
