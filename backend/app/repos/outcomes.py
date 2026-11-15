"""Program outcomes for the funder export (RPT-3). Members read; writing needs `programs.manage`."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.authz.policy import Action, can
from app.db.models import Program, ProgramOutcome
from app.errors import Forbidden, Invalid


def _require_member(actor: Actor) -> None:
    if actor.kind not in ("user", "cli"):
        raise Forbidden("Not allowed to read program outcomes.")


def list_all(db: Session, actor: Actor) -> list[tuple[ProgramOutcome, Program]]:
    _require_member(actor)
    stmt = (
        select(ProgramOutcome, Program)
        .join(Program, Program.id == ProgramOutcome.program_id)
        .order_by(ProgramOutcome.period_start.desc(), Program.name, ProgramOutcome.id)
    )
    return [(o, p) for o, p in db.execute(stmt).all()]


def for_programs(
    db: Session, actor: Actor, *, program_ids: list[int], start: date, end: date
) -> list[tuple[ProgramOutcome, Program]]:
    """Outcomes for these programs whose period overlaps [start, end]."""
    _require_member(actor)
    if not program_ids:
        return []
    stmt = (
        select(ProgramOutcome, Program)
        .join(Program, Program.id == ProgramOutcome.program_id)
        .where(
            ProgramOutcome.program_id.in_(program_ids),
            ProgramOutcome.period_start <= end,
            ProgramOutcome.period_end >= start,
        )
        .order_by(Program.name, ProgramOutcome.period_start, ProgramOutcome.id)
    )
    return [(o, p) for o, p in db.execute(stmt).all()]


def create(
    db: Session,
    actor: Actor,
    *,
    program_id: int,
    period_start: date,
    period_end: date,
    metric_label: str,
    value: object,
    unit: str,
    source_note: str | None,
) -> tuple[ProgramOutcome, Program]:
    if not can(actor, Action.PROGRAMS_MANAGE):
        raise Forbidden("Only a super admin can enter outcomes while one is active.")
    program = db.get(Program, program_id)
    if program is None:
        raise Invalid("That program does not exist.")
    if period_end < period_start:
        raise Invalid("The period must end on or after its start.")
    row = ProgramOutcome(
        program_id=program_id,
        period_start=period_start,
        period_end=period_end,
        metric_label=metric_label,
        value=value,
        unit=unit,
        source_note=source_note,
    )
    db.add(row)
    db.flush()
    return row, program
