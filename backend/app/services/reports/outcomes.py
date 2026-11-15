"""Program outcomes entered by hand (RPT-3)."""

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import Program, ProgramOutcome
from app.errors import Invalid
from app.repos import audit, outcomes
from app.schemas.settings import OutcomeIn, OutcomeListOut, OutcomeOut, ProgramOut
from app.services.ingest.uploads import UnsupportedUpload, UploadTooLarge, read_table


def to_out(o: ProgramOutcome, p: Program) -> OutcomeOut:
    return OutcomeOut(
        id=o.id,
        program=ProgramOut(id=p.id, name=p.name, slug=p.slug, is_active=p.is_active),
        period_start=o.period_start,
        period_end=o.period_end,
        metric_label=o.metric_label,
        value=o.value,
        unit=o.unit,
        source_note=o.source_note,
    )


def list_outcomes(db: Session, actor: Actor) -> OutcomeListOut:
    return OutcomeListOut(items=[to_out(o, p) for o, p in outcomes.list_all(db, actor)])


def create_outcome(db: Session, actor: Actor, body: OutcomeIn) -> OutcomeOut:
    row, program = outcomes.create(db, actor, **body.model_dump())
    audit.write(
        db, actor, "outcome.create", entity="program_outcome", entity_id=row.id,
        data={"program_id": program.id, "metric_label": row.metric_label},
    )  # fmt: skip
    return to_out(row, program)


UPLOAD_MAX_BYTES = 1024 * 1024
UPLOAD_COLUMNS = ("program", "period_start", "period_end", "metric_label", "value", "unit")
UPLOAD_OPTIONAL = ("source_note",)
MAX_PROBLEMS_SHOWN = 10


def _cell(row: list[object], index: dict[str, int], name: str) -> str:
    i = index.get(name)
    return str(row[i]).strip() if i is not None and i < len(row) else ""


def upload_outcomes(db: Session, actor: Actor, filename: str, data: bytes) -> OutcomeListOut:
    """All or nothing: one bad row rejects the file and names the rows (RPT-3)."""
    outcomes.require_manage(actor)
    if not filename.lower().endswith(".csv"):
        raise UnsupportedUpload("Upload a CSV file.")
    if len(data) > UPLOAD_MAX_BYTES:
        raise UploadTooLarge("File must be at most 1 MB.")
    table = read_table(filename, data)
    header = [str(h).strip().lower() for h in table[0][1]]
    missing = [c for c in UPLOAD_COLUMNS if c not in header]
    if missing:
        raise Invalid("Missing column(s): " + ", ".join(missing) + ".")
    index = {
        name: header.index(name) for name in (*UPLOAD_COLUMNS, *UPLOAD_OPTIONAL) if name in header
    }
    problems: list[str] = []
    parsed: list[OutcomeIn] = []
    for number, row in table[1:]:
        values = {c: _cell(row, index, c) for c in (*UPLOAD_COLUMNS, *UPLOAD_OPTIONAL)}
        program = outcomes.program_by_name(db, actor, values["program"])
        if program is None:
            problems.append(f"row {number + 1}: unknown program '{values['program'][:40]}'")
            continue
        try:
            parsed.append(
                OutcomeIn.model_validate(
                    {
                        **values,
                        "program_id": program.id,
                        "source_note": values["source_note"] or None,
                    }
                )
            )
        except ValidationError as exc:
            bad = ", ".join(str(e["loc"][0]) for e in exc.errors())
            problems.append(f"row {number + 1}: check {bad}")
    if not parsed and not problems:
        raise Invalid("The file has no data rows.")
    if problems:
        extra = len(problems) - MAX_PROBLEMS_SHOWN
        shown = "; ".join(problems[:MAX_PROBLEMS_SHOWN]) + (
            f"; and {extra} more" if extra > 0 else ""
        )
        raise Invalid(f"Nothing was saved. {shown}")
    created = [create_outcome(db, actor, body) for body in parsed]
    audit.write(db, actor, "outcome.upload", entity="program_outcome", data={"rows": len(created)})
    return OutcomeListOut(items=created)
